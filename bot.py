#!/usr/bin/env python3
"""
DM BOT - Discord Direct Message Bot with Loop
Features: !dm @user message, !loop delay, !stoploop, whitelist
"""

import discord
from discord.ext import commands, tasks
import os
import asyncio
import json
from datetime import datetime

# ============================================
# CONFIGURATION - READ FROM ENVIRONMENT
# ============================================

DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')

if not DISCORD_TOKEN:
    print("❌ ERROR: DISCORD_TOKEN not set in Railway Variables!")
    exit(1)

# ============================================
# WHITELIST - ONLY THESE USERS CAN USE THE BOT
# ============================================

# ADD YOUR DISCORD USER ID HERE
WHITELISTED_USERS = [
    "1218033158877089953",  # REPLACE WITH YOUR ACTUAL DISCORD USER ID
]

WHITELIST_FILE = "dm_whitelist.json"

def load_whitelist():
    if os.path.exists(WHITELIST_FILE):
        try:
            with open(WHITELIST_FILE, 'r') as f:
                data = json.load(f)
                return data.get("whitelisted_users", WHITELISTED_USERS)
        except:
            pass
    return WHITELISTED_USERS

def save_whitelist(whitelist):
    with open(WHITELIST_FILE, 'w') as f:
        json.dump({"whitelisted_users": whitelist}, f, indent=2)

WHITELISTED_USERS = load_whitelist()

def is_whitelisted(user_id):
    return str(user_id) in WHITELISTED_USERS

def get_whitelist_display():
    if not WHITELISTED_USERS:
        return "No users whitelisted"
    mentions = [f"<@{uid}>" for uid in WHITELISTED_USERS]
    return ", ".join(mentions)

# ============================================
# DISCORD BOT SETUP
# ============================================

intents = discord.Intents.default()
intents.message_content = True
intents.messages = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Loop settings per user
loop_tasks = {}  # user_id: {"task": task, "delay": seconds, "target": user_id, "message": str, "running": bool}
loop_delays = {}  # user_id: delay in seconds

# ============================================
# HELPER FUNCTIONS
# ============================================

async def send_dm(target_user, message, sender):
    """Send a DM to a user with error handling"""
    try:
        await target_user.send(message)
        return True, "DM sent successfully"
    except discord.Forbidden:
        return False, "Cannot DM this user (DMs closed or bot blocked)"
    except discord.HTTPException as e:
        return False, f"Failed to send: {e}"
    except Exception as e:
        return False, f"Error: {e}"

async def send_and_log(ctx, target_user, message, status, error=None):
    """Send confirmation and log the action"""
    if status:
        await ctx.send(f"✅ DM sent to {target_user.mention}")
        print(f"[DM] {ctx.author} -> {target_user}: {message[:50]}...")
    else:
        await ctx.send(f"❌ Failed to send DM to {target_user.mention}\nReason: {error}")

# ============================================
# CORE COMMANDS
# ============================================

@bot.event
async def on_ready():
    print("="*50)
    print("✅ DM BOT - READY")
    print(f"🤖 Logged in as: {bot.user.name}")
    print(f"👥 Whitelisted Users: {len(WHITELISTED_USERS)}")
    print("="*50)

@bot.command(name="dm")
async def dm_command(ctx, user: discord.User, *, message: str):
    """
    Send a direct message to a user.
    Usage: !dm @user Hello there!
    """
    if not is_whitelisted(ctx.author.id):
        await ctx.send(f"❌ **Access Denied**\n\nWhitelisted users: {get_whitelist_display()}")
        return
    
    if not message:
        await ctx.send("❓ Please provide a message.\nUsage: `!dm @user Your message here`")
        return
    
    # Show typing indicator
    async with ctx.typing():
        status, result = await send_dm(user, message, ctx.author)
        
        if status:
            await ctx.send(f"✅ DM sent to {user.mention}")
            print(f"[DM] {ctx.author} -> {user}: {message[:50]}...")
        else:
            await ctx.send(f"❌ Failed to send DM to {user.mention}\nReason: {result}")

@bot.command(name="dm_raw")
async def dm_raw_command(ctx, user_id: str, *, message: str):
    """
    Send DM using user ID (useful if user not in server)
    Usage: !dm_raw 123456789012345678 Hello!
    """
    if not is_whitelisted(ctx.author.id):
        await ctx.send("❌ Access Denied.")
        return
    
    try:
        user = await bot.fetch_user(int(user_id))
        status, result = await send_dm(user, message, ctx.author)
        
        if status:
            await ctx.send(f"✅ DM sent to {user.mention} (ID: {user_id})")
        else:
            await ctx.send(f"❌ Failed: {result}")
    except discord.NotFound:
        await ctx.send(f"❌ User with ID `{user_id}` not found.")
    except ValueError:
        await ctx.send("❌ Invalid user ID. Must be numbers only.")
    except Exception as e:
        await ctx.send(f"❌ Error: {e}")

# ============================================
# LOOP COMMANDS
# ============================================

@bot.command(name="loop")
async def start_loop(ctx, delay: float = None, user: discord.User = None, *, message: str = None):
    """
    Start a loop that sends DMs repeatedly.
    Usage: !loop 0.5 @user Hello! (sends every 0.5 seconds)
           !loop 2 @user Hi! (sends every 2 seconds)
    """
    if not is_whitelisted(ctx.author.id):
        await ctx.send("❌ Access Denied.")
        return
    
    user_id = str(ctx.author.id)
    
    # Show current loop status if no parameters
    if delay is None:
        if user_id in loop_tasks and loop_tasks[user_id].get("running", False):
            current_delay = loop_tasks[user_id].get("delay", "?")
            current_target = loop_tasks[user_id].get("target", "?")
            current_message = loop_tasks[user_id].get("message", "?")[:50]
            await ctx.send(f"🔄 **Loop Active**\n"
                          f"Delay: {current_delay} seconds\n"
                          f"Target: <@{current_target}>\n"
                          f"Message: {current_message}...\n"
                          f"Use `!stoploop` to stop.")
        else:
            await ctx.send("No active loop. Start one with:\n`!loop 0.5 @user Your message`")
        return
    
    # Validate parameters
    if delay <= 0:
        await ctx.send("❌ Delay must be greater than 0 seconds.")
        return
    
    if delay < 0.5:
        await ctx.send("⚠️ Very fast loop! (less than 0.5s). Discord may rate limit you.")
    
    if user is None:
        await ctx.send("❓ Please specify a user.\nUsage: `!loop 0.5 @user Your message`")
        return
    
    if message is None:
        await ctx.send("❓ Please specify a message.\nUsage: `!loop 0.5 @user Your message`")
        return
    
    # Stop existing loop if running
    if user_id in loop_tasks and loop_tasks[user_id].get("running", False):
        loop_tasks[user_id]["running"] = False
        if "task" in loop_tasks[user_id]:
            loop_tasks[user_id]["task"].cancel()
        await asyncio.sleep(0.5)
    
    # Store loop settings
    loop_tasks[user_id] = {
        "running": True,
        "delay": delay,
        "target": user.id,
        "target_name": str(user),
        "message": message,
        "count": 0
    }
    
    # Start the loop task
    async def dm_loop():
        while loop_tasks[user_id].get("running", False):
            try:
                target_user = bot.get_user(loop_tasks[user_id]["target"])
                if not target_user:
                    try:
                        target_user = await bot.fetch_user(loop_tasks[user_id]["target"])
                    except:
                        await ctx.send(f"❌ Loop stopped: Cannot find user.")
                        break
                
                # Send DM
                try:
                    await target_user.send(loop_tasks[user_id]["message"])
                    loop_tasks[user_id]["count"] += 1
                    print(f"[LOOP] {ctx.author} -> {target_user}: {loop_tasks[user_id]['count']} messages sent")
                except discord.Forbidden:
                    await ctx.send(f"❌ Loop stopped: Cannot DM {target_user.mention} (DMs closed)")
                    break
                except Exception as e:
                    print(f"[LOOP ERROR] {e}")
                
                # Wait for next iteration
                await asyncio.sleep(loop_tasks[user_id]["delay"])
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[LOOP ERROR] {e}")
                await asyncio.sleep(1)
    
    # Create and store task
    task = asyncio.create_task(dm_loop())
    loop_tasks[user_id]["task"] = task
    
    await ctx.send(f"🔄 **Loop Started**\n"
                  f"📡 Sending to: {user.mention}\n"
                  f"⏱️ Delay: {delay} seconds\n"
                  f"💬 Message: {message[:100]}\n"
                  f"🛑 Use `!stoploop` to stop.")

@bot.command(name="stoploop", aliases=["stop", "stopsending"])
async def stop_loop(ctx):
    """Stop the active DM loop"""
    if not is_whitelisted(ctx.author.id):
        await ctx.send("❌ Access Denied.")
        return
    
    user_id = str(ctx.author.id)
    
    if user_id not in loop_tasks or not loop_tasks[user_id].get("running", False):
        await ctx.send("❌ No active loop to stop.")
        return
    
    # Stop the loop
    count = loop_tasks[user_id].get("count", 0)
    loop_tasks[user_id]["running"] = False
    
    if "task" in loop_tasks[user_id]:
        loop_tasks[user_id]["task"].cancel()
    
    await ctx.send(f"🛑 **Loop Stopped**\n"
                  f"📊 Total messages sent: {count}\n"
                  f"✅ Loop has been terminated.")

@bot.command(name="loopstatus")
async def loop_status(ctx):
    """Check current loop status"""
    if not is_whitelisted(ctx.author.id):
        await ctx.send("❌ Access Denied.")
        return
    
    user_id = str(ctx.author.id)
    
    if user_id in loop_tasks and loop_tasks[user_id].get("running", False):
        current_delay = loop_tasks[user_id].get("delay", "?")
        current_target = loop_tasks[user_id].get("target", "?")
        current_message = loop_tasks[user_id].get("message", "?")
        count = loop_tasks[user_id].get("count", 0)
        
        await ctx.send(f"🔄 **Loop Status: ACTIVE**\n"
                      f"⏱️ Delay: {current_delay} seconds\n"
                      f"👤 Target: <@{current_target}>\n"
                      f"📨 Messages sent: {count}\n"
                      f"💬 Message: {current_message[:100]}...\n"
                      f"🛑 Use `!stoploop` to stop.")
    else:
        await ctx.send("✅ No active loop.")

# ============================================
# WHITELIST MANAGEMENT
# ============================================

@bot.command(name="adddmuser")
async def add_dm_user(ctx, user_id: str = None):
    """Add a user to the DM bot whitelist"""
    if not is_whitelisted(ctx.author.id):
        await ctx.send("❌ Access Denied.")
        return
    
    if not user_id:
        await ctx.send("❓ Usage: `!adddmuser 123456789012345678`")
        return
    
    user_id = user_id.replace("<@", "").replace(">", "").replace("!", "")
    
    if user_id in WHITELISTED_USERS:
        await ctx.send(f"⚠️ User already whitelisted.")
        return
    
    WHITELISTED_USERS.append(user_id)
    save_whitelist(WHITELISTED_USERS)
    await ctx.send(f"✅ User added to DM bot whitelist.")

@bot.command(name="removedmuser")
async def remove_dm_user(ctx, user_id: str = None):
    """Remove a user from the DM bot whitelist"""
    if not is_whitelisted(ctx.author.id):
        await ctx.send("❌ Access Denied.")
        return
    
    if not user_id:
        await ctx.send("❓ Usage: `!removedmuser 123456789012345678`")
        return
    
    user_id = user_id.replace("<@", "").replace(">", "").replace("!", "")
    
    if user_id not in WHITELISTED_USERS:
        await ctx.send(f"⚠️ User not whitelisted.")
        return
    
    WHITELISTED_USERS.remove(user_id)
    save_whitelist(WHITELISTED_USERS)
    await ctx.send(f"✅ User removed from DM bot whitelist.")

@bot.command(name="dmusers")
async def list_dm_users(ctx):
    """List all whitelisted DM bot users"""
    if not is_whitelisted(ctx.author.id):
        await ctx.send("❌ Access Denied.")
        return
    
    if not WHITELISTED_USERS:
        await ctx.send("No users whitelisted.")
        return
    
    user_list = []
    for uid in WHITELISTED_USERS:
        try:
            user = await bot.fetch_user(int(uid))
            user_list.append(f"{user.mention}")
        except:
            user_list.append(f"Unknown User (`{uid}`)")
    
    await ctx.send(f"**👥 Whitelisted DM Users:**\n{', '.join(user_list)}")

# ============================================
# INFO COMMANDS
# ============================================

@bot.command(name="ping")
async def ping(ctx):
    """Check bot latency"""
    await ctx.send(f"🏓 Pong! Latency: {round(bot.latency * 1000)}ms")

@bot.command(name="helpdm")
async def help_command(ctx):
    """Show all DM bot commands"""
    embed = discord.Embed(
        title="💬 DM Bot - Commands",
        description="**Whitelist Protected** - Only approved users can use these commands.",
        color=discord.Color.blue()
    )
    embed.add_field(
        name="📨 Direct Message",
        value="`!dm @user <message>` - Send a single DM\n"
              "`!dm_raw <user_id> <message>` - Send DM by ID",
        inline=False
    )
    embed.add_field(
        name="🔄 Loop Commands",
        value="`!loop <delay> @user <message>` - Start DM loop\n"
              "`!stoploop` - Stop current loop\n"
              "`!loopstatus` - Check loop status",
        inline=False
    )
    embed.add_field(
        name="👥 Whitelist",
        value="`!dmusers` - List whitelisted users\n"
              "`!adddmuser <id>` - Add user\n"
              "`!removedmuser <id>` - Remove user",
        inline=False
    )
    embed.add_field(
        name="ℹ️ Info",
        value="`!ping` - Check latency\n"
              "`!helpdm` - Show this menu",
        inline=False
    )
    embed.set_footer(text="Loop delays can be as low as 0.5 seconds. Use responsibly!")
    await ctx.send(embed=embed)

# ============================================
# ERROR HANDLING
# ============================================

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("❓ Missing argument. Use `!helpdm`")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("❓ Invalid user. Make sure to @mention them.")
    elif isinstance(error, commands.CommandNotFound):
        pass
    else:
        await ctx.send(f"❌ Error: {str(error)}")

# ============================================
# RUN BOT
# ============================================

if __name__ == "__main__":
    print("🚀 Starting DM Bot...")
    bot.run(DISCORD_TOKEN)
