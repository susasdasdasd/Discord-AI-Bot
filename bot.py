#!/usr/bin/env python3
"""
MODERATION BOT v2.0 - Discord Moderation Tool
"""

import discord
from discord.ext import commands
import json
import os
import asyncio
from datetime import datetime, timedelta

# ============================================
# CONFIGURATION - READ FROM ENVIRONMENT
# ============================================

DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')

if not DISCORD_TOKEN:
    raise ValueError("❌ DISCORD_TOKEN environment variable not set!\n"
                     "   Add it in Railway: Variables tab -> DISCORD_TOKEN")
# Default delay for purge confirmation (seconds)
DEFAULT_DELAY = 2

# Log channel ID (optional - set to None to disable)
LOG_CHANNEL_ID = None  # Replace with channel ID for moderation logs

# ============================================
# WHITELIST CONFIGURATION
# ============================================

WHITELISTED_USERS = [
    "1218033158877089953",  # REPLACE WITH YOUR ACTUAL DISCORD USER ID
]

WHITELIST_FILE = "mod_whitelist.json"

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

# Store moderation settings per guild
guild_settings = {}

class ModSettings:
    def __init__(self):
        self.purge_delay = DEFAULT_DELAY
        self.log_channel = None
        self.warned_users = {}  # user_id: [warnings, reasons]

# Load settings
def load_guild_settings():
    if os.path.exists("guild_settings.json"):
        try:
            with open("guild_settings.json", 'r') as f:
                return json.load(f)
        except:
            pass
    return {}

def save_guild_settings():
    with open("guild_settings.json", 'w') as f:
        json.dump(guild_settings, f, indent=2)

# Initialize guild_settings from file
guild_settings = load_guild_settings()

# ============================================
# HELPER FUNCTIONS
# ============================================

async def log_action(guild, action, moderator, target=None, reason=None, details=None):
    """Log moderation actions to configured channel"""
    log_channel_id = guild_settings.get(str(guild.id), {}).get("log_channel")
    
    if not log_channel_id:
        return
    
    log_channel = guild.get_channel(int(log_channel_id))
    if not log_channel:
        return
    
    embed = discord.Embed(
        title=f"📋 {action}",
        timestamp=datetime.utcnow(),
        color=discord.Color.orange() if "WARN" in action else discord.Color.blue()
    )
    embed.add_field(name="Moderator", value=moderator.mention, inline=True)
    if target:
        embed.add_field(name="Target", value=target, inline=True)
    if reason:
        embed.add_field(name="Reason", value=reason, inline=True)
    if details:
        embed.add_field(name="Details", value=details, inline=True)
    
    await log_channel.send(embed=embed)

async def send_and_delete(ctx, message, delay=None):
    """Send a message and delete it after delay"""
    if delay is None:
        delay = guild_settings.get(str(ctx.guild.id), {}).get("purge_delay", DEFAULT_DELAY)
    msg = await ctx.send(message)
    await msg.delete(delay=delay)

# ============================================
# PURGE COMMANDS
# ============================================

@bot.event
async def on_ready():
    print("="*50)
    print("MODERATION BOT v2.0 - READY")
    print(f"Logged in as: {bot.user.name}")
    print(f"Whitelisted Users: {len(WHITELISTED_USERS)}")
    print(f"Default Purge Delay: {DEFAULT_DELAY}s")
    print("="*50)

@bot.command(name="purge", aliases=["clear", "clean"])
async def purge_messages(ctx, amount: int = None):
    """
    Delete a specified number of messages with delay.
    Usage: !purge 50
    """
    if not is_whitelisted(ctx.author.id):
        await ctx.send(f"❌ **Access Denied**\n\nWhitelisted users: {get_whitelist_display()}")
        return
    
    if amount is None:
        await ctx.send("❓ Usage: `!purge 50`")
        return
    
    if amount <= 0:
        await ctx.send("❌ Please specify a positive number.")
        return
    
    if amount > 1000:
        amount = 1000
        await ctx.send("⚠️ Max 1000 messages. Using 1000.")
    
    if not ctx.author.guild_permissions.manage_messages:
        await ctx.send("❌ You need `Manage Messages` permission.")
        return
    
    if not ctx.me.guild_permissions.manage_messages:
        await ctx.send("❌ I need `Manage Messages` permission.")
        return
    
    # Get delay from settings
    delay = guild_settings.get(str(ctx.guild.id), {}).get("purge_delay", DEFAULT_DELAY)
    
    # Send confirmation with countdown
    confirm_msg = await ctx.send(f"⚠️ **PURGE INITIATED**\nDeleting {amount} messages in {delay} seconds...")
    
    # Wait for delay
    await asyncio.sleep(delay)
    
    # Delete messages
    try:
        deleted = await ctx.channel.purge(limit=amount + 2)  # +2 for confirm and command
        await send_and_delete(ctx, f"✅ Deleted {len(deleted) - 2} messages.", 3)
        
        # Log action
        await log_action(ctx.guild, "PURGE", ctx.author, 
                        details=f"Channel: #{ctx.channel.name}\nMessages: {len(deleted) - 2}")
        
    except Exception as e:
        await ctx.send(f"❌ Error: {e}")

@bot.command(name="purgeuser", aliases=["clearuser"])
async def purge_user_messages(ctx, user: discord.User, amount: int = 50):
    """Delete messages from a specific user"""
    if not is_whitelisted(ctx.author.id):
        await ctx.send("❌ Access Denied.")
        return
    
    if not ctx.author.guild_permissions.manage_messages:
        await ctx.send("❌ You need `Manage Messages` permission.")
        return
    
    if amount > 500:
        amount = 500
    
    delay = guild_settings.get(str(ctx.guild.id), {}).get("purge_delay", DEFAULT_DELAY)
    
    await ctx.send(f"⚠️ Deleting {amount} messages from {user.mention} in {delay}s...")
    await asyncio.sleep(delay)
    
    def is_user(message):
        return message.author == user
    
    try:
        deleted = await ctx.channel.purge(limit=amount + 1, check=is_user)
        await send_and_delete(ctx, f"✅ Deleted {len(deleted) - 1} messages from {user.mention}.", 3)
        await log_action(ctx.guild, "PURGE USER", ctx.author, user.mention, 
                        details=f"Channel: #{ctx.channel.name}\nMessages: {len(deleted) - 1}")
    except Exception as e:
        await ctx.send(f"❌ Error: {e}")

@bot.command(name="purgebot")
async def purge_bot_messages(ctx, amount: int = 50):
    """Delete bot's own messages"""
    if not is_whitelisted(ctx.author.id):
        await ctx.send("❌ Access Denied.")
        return
    
    if amount > 500:
        amount = 500
    
    delay = guild_settings.get(str(ctx.guild.id), {}).get("purge_delay", DEFAULT_DELAY)
    
    await ctx.send(f"⚠️ Deleting {amount} of my messages in {delay}s...")
    await asyncio.sleep(delay)
    
    def is_bot(message):
        return message.author == bot.user
    
    try:
        deleted = await ctx.channel.purge(limit=amount + 1, check=is_bot)
        await log_action(ctx.guild, "PURGE BOT", ctx.author, 
                        details=f"Channel: #{ctx.channel.name}\nMessages: {len(deleted) - 1}")
    except Exception as e:
        await ctx.send(f"❌ Error: {e}")

# ============================================
# SLOWMODE COMMANDS
# ============================================

@bot.command(name="slowmode", aliases=["sm"])
async def set_slowmode(ctx, seconds: int = None):
    """
    Set slowmode for the current channel.
    Usage: !slowmode 5 (5 seconds)
    !slowmode 0 to disable
    """
    if not is_whitelisted(ctx.author.id):
        await ctx.send("❌ Access Denied.")
        return
    
    if not ctx.author.guild_permissions.manage_channels:
        await ctx.send("❌ You need `Manage Channels` permission.")
        return
    
    if seconds is None:
        current = ctx.channel.slowmode_delay
        await ctx.send(f"⏱️ Current slowmode: {current} seconds")
        return
    
    if seconds < 0 or seconds > 21600:
        await ctx.send("❌ Slowmode must be between 0 and 21600 seconds (6 hours).")
        return
    
    try:
        await ctx.channel.edit(slowmode_delay=seconds)
        if seconds == 0:
            await ctx.send(f"✅ Slowmode disabled.")
        else:
            await ctx.send(f"✅ Slowmode set to {seconds} seconds.")
        await log_action(ctx.guild, "SLOWMODE", ctx.author, 
                        details=f"Channel: #{ctx.channel.name}\nSlowmode: {seconds}s")
    except Exception as e:
        await ctx.send(f"❌ Error: {e}")

# ============================================
# LOCKDOWN COMMANDS
# ============================================

@bot.command(name="lock", aliases=["lockdown"])
async def lock_channel(ctx):
    """Lock the current channel (prevent sending messages)"""
    if not is_whitelisted(ctx.author.id):
        await ctx.send("❌ Access Denied.")
        return
    
    if not ctx.author.guild_permissions.manage_channels:
        await ctx.send("❌ You need `Manage Channels` permission.")
        return
    
    try:
        # Get default role (@everyone)
        default_role = ctx.guild.default_role
        
        # Set permissions to deny send messages
        await ctx.channel.set_permissions(default_role, send_messages=False)
        await ctx.send("🔒 **Channel Locked**\nNo one can send messages until unlocked.")
        await log_action(ctx.guild, "LOCK CHANNEL", ctx.author, 
                        details=f"Channel: #{ctx.channel.name}")
    except Exception as e:
        await ctx.send(f"❌ Error: {e}")

@bot.command(name="unlock")
async def unlock_channel(ctx):
    """Unlock the current channel"""
    if not is_whitelisted(ctx.author.id):
        await ctx.send("❌ Access Denied.")
        return
    
    if not ctx.author.guild_permissions.manage_channels:
        await ctx.send("❌ You need `Manage Channels` permission.")
        return
    
    try:
        default_role = ctx.guild.default_role
        await ctx.channel.set_permissions(default_role, send_messages=None)
        await ctx.send("🔓 **Channel Unlocked**\nMessages can now be sent.")
        await log_action(ctx.guild, "UNLOCK CHANNEL", ctx.author, 
                        details=f"Channel: #{ctx.channel.name}")
    except Exception as e:
        await ctx.send(f"❌ Error: {e}")

# ============================================
# WARN SYSTEM
# ============================================

@bot.command(name="warn")
async def warn_user(ctx, user: discord.User, *, reason: str = "No reason provided"):
    """Warn a user (tracks warnings)"""
    if not is_whitelisted(ctx.author.id):
        await ctx.send("❌ Access Denied.")
        return
    
    if not ctx.author.guild_permissions.kick_members:
        await ctx.send("❌ You need `Kick Members` permission.")
        return
    
    guild_id = str(ctx.guild.id)
    
    if guild_id not in guild_settings:
        guild_settings[guild_id] = {}
    
    if "warned_users" not in guild_settings[guild_id]:
        guild_settings[guild_id]["warned_users"] = {}
    
    user_id = str(user.id)
    warnings = guild_settings[guild_id]["warned_users"].get(user_id, [])
    warnings.append({
        "reason": reason,
        "moderator": str(ctx.author.id),
        "timestamp": datetime.utcnow().isoformat()
    })
    guild_settings[guild_id]["warned_users"][user_id] = warnings
    save_guild_settings()
    
    await ctx.send(f"⚠️ **{user.mention} has been warned**\nReason: {reason}\nTotal warnings: {len(warnings)}")
    
    # Try to DM user
    try:
        await user.send(f"⚠️ You have been warned in **{ctx.guild.name}**\nReason: {reason}\nWarnings: {len(warnings)}")
    except:
        pass
    
    await log_action(ctx.guild, "WARN", ctx.author, user.mention, reason)

@bot.command(name="warnings")
async def check_warnings(ctx, user: discord.User = None):
    """Check warnings for a user"""
    if not is_whitelisted(ctx.author.id):
        await ctx.send("❌ Access Denied.")
        return
    
    if user is None:
        user = ctx.author
    
    guild_id = str(ctx.guild.id)
    user_id = str(user.id)
    
    warnings = guild_settings.get(guild_id, {}).get("warned_users", {}).get(user_id, [])
    
    if not warnings:
        await ctx.send(f"✅ {user.mention} has no warnings.")
        return
    
    embed = discord.Embed(
        title=f"⚠️ Warnings for {user.display_name}",
        color=discord.Color.orange()
    )
    
    for i, warn in enumerate(warnings[-5:], 1):  # Show last 5
        embed.add_field(
            name=f"Warning #{i}",
            value=f"Reason: {warn['reason']}\nDate: {warn['timestamp'][:10]}",
            inline=False
        )
    
    embed.set_footer(text=f"Total warnings: {len(warnings)}")
    await ctx.send(embed=embed)

@bot.command(name="clearwarns")
async def clear_warnings(ctx, user: discord.User):
    """Clear all warnings for a user"""
    if not is_whitelisted(ctx.author.id):
        await ctx.send("❌ Access Denied.")
        return
    
    if not ctx.author.guild_permissions.kick_members:
        await ctx.send("❌ You need `Kick Members` permission.")
        return
    
    guild_id = str(ctx.guild.id)
    user_id = str(user.id)
    
    if guild_id in guild_settings and user_id in guild_settings[guild_id].get("warned_users", {}):
        del guild_settings[guild_id]["warned_users"][user_id]
        save_guild_settings()
        await ctx.send(f"✅ Cleared all warnings for {user.mention}")
        await log_action(ctx.guild, "CLEAR WARNINGS", ctx.author, user.mention)
    else:
        await ctx.send(f"✅ {user.mention} has no warnings to clear.")

# ============================================
# SETTINGS COMMANDS
# ============================================

@bot.command(name="setdelay")
async def set_purge_delay(ctx, seconds: int = None):
    """Set the delay before purge executes (default: 2s)"""
    if not is_whitelisted(ctx.author.id):
        await ctx.send("❌ Access Denied.")
        return
    
    if seconds is None:
        current = guild_settings.get(str(ctx.guild.id), {}).get("purge_delay", DEFAULT_DELAY)
        await ctx.send(f"⏱️ Current purge delay: {current} seconds")
        return
    
    if seconds < 0 or seconds > 30:
        await ctx.send("❌ Delay must be between 0 and 30 seconds.")
        return
    
    if str(ctx.guild.id) not in guild_settings:
        guild_settings[str(ctx.guild.id)] = {}
    
    guild_settings[str(ctx.guild.id)]["purge_delay"] = seconds
    save_guild_settings()
    
    await ctx.send(f"✅ Purge delay set to {seconds} seconds.")
    await log_action(ctx.guild, "SET DELAY", ctx.author, details=f"Delay: {seconds}s")

@bot.command(name="setlog")
async def set_log_channel(ctx, channel: discord.TextChannel = None):
    """Set the logging channel for moderation actions"""
    if not is_whitelisted(ctx.author.id):
        await ctx.send("❌ Access Denied.")
        return
    
    if not ctx.author.guild_permissions.administrator:
        await ctx.send("❌ You need `Administrator` permission.")
        return
    
    if channel is None:
        channel = ctx.channel
    
    if str(ctx.guild.id) not in guild_settings:
        guild_settings[str(ctx.guild.id)] = {}
    
    guild_settings[str(ctx.guild.id)]["log_channel"] = str(channel.id)
    save_guild_settings()
    
    await ctx.send(f"✅ Log channel set to {channel.mention}")
    await log_action(ctx.guild, "SET LOG CHANNEL", ctx.author, details=f"Channel: {channel.name}")

# ============================================
# MEMBER MANAGEMENT
# ============================================

@bot.command(name="kick")
async def kick_user(ctx, user: discord.Member, *, reason: str = "No reason provided"):
    """Kick a user from the server"""
    if not is_whitelisted(ctx.author.id):
        await ctx.send("❌ Access Denied.")
        return
    
    if not ctx.author.guild_permissions.kick_members:
        await ctx.send("❌ You need `Kick Members` permission.")
        return
    
    if user == ctx.author:
        await ctx.send("❌ You cannot kick yourself.")
        return
    
    delay = guild_settings.get(str(ctx.guild.id), {}).get("purge_delay", DEFAULT_DELAY)
    
    await ctx.send(f"⚠️ Kicking {user.mention} in {delay} seconds...")
    await asyncio.sleep(delay)
    
    try:
        await user.kick(reason=f"{reason} - Kicked by {ctx.author}")
        await send_and_delete(ctx, f"✅ Kicked {user.mention}\nReason: {reason}", 5)
        await log_action(ctx.guild, "KICK", ctx.author, user.mention, reason)
    except Exception as e:
        await ctx.send(f"❌ Error: {e}")

@bot.command(name="ban")
async def ban_user(ctx, user: discord.User, *, reason: str = "No reason provided"):
    """Ban a user from the server"""
    if not is_whitelisted(ctx.author.id):
        await ctx.send("❌ Access Denied.")
        return
    
    if not ctx.author.guild_permissions.ban_members:
        await ctx.send("❌ You need `Ban Members` permission.")
        return
    
    delay = guild_settings.get(str(ctx.guild.id), {}).get("purge_delay", DEFAULT_DELAY)
    
    await ctx.send(f"⚠️ Banning {user.mention} in {delay} seconds...")
    await asyncio.sleep(delay)
    
    try:
        await ctx.guild.ban(user, reason=f"{reason} - Banned by {ctx.author}")
        await send_and_delete(ctx, f"✅ Banned {user.mention}\nReason: {reason}", 5)
        await log_action(ctx.guild, "BAN", ctx.author, user.mention, reason)
    except Exception as e:
        await ctx.send(f"❌ Error: {e}")

@bot.command(name="timeout")
async def timeout_user(ctx, user: discord.Member, minutes: int = 5, *, reason: str = "No reason provided"):
    """Timeout a user for specified minutes"""
    if not is_whitelisted(ctx.author.id):
        await ctx.send("❌ Access Denied.")
        return
    
    if not ctx.author.guild_permissions.moderate_members:
        await ctx.send("❌ You need `Moderate Members` permission.")
        return
    
    if minutes > 40320:  # 28 days max
        await ctx.send("❌ Timeout cannot exceed 28 days (40320 minutes).")
        return
    
    duration = timedelta(minutes=minutes)
    
    try:
        await user.timeout(duration, reason=f"{reason} - Timed out by {ctx.author}")
        await ctx.send(f"⏰ **{user.mention} timed out for {minutes} minutes**\nReason: {reason}")
        await log_action(ctx.guild, "TIMEOUT", ctx.author, user.mention, reason, details=f"Duration: {minutes} minutes")
    except Exception as e:
        await ctx.send(f"❌ Error: {e}")

# ============================================
# WHITELIST MANAGEMENT
# ============================================

@bot.command(name="addmod")
async def add_to_whitelist(ctx, user_id: str = None):
    """Add a user to the moderation whitelist"""
    if not is_whitelisted(ctx.author.id):
        await ctx.send("❌ Access Denied.")
        return
    
    if not user_id:
        await ctx.send("❓ Usage: `!addmod 123456789012345678`")
        return
    
    user_id = user_id.replace("<@", "").replace(">", "").replace("!", "")
    
    if user_id in WHITELISTED_USERS:
        await ctx.send(f"⚠️ User <@{user_id}> is already whitelisted.")
        return
    
    WHITELISTED_USERS.append(user_id)
    save_whitelist(WHITELISTED_USERS)
    
    await ctx.send(f"✅ User <@{user_id}> has been added to the moderation whitelist.")

@bot.command(name="removemod")
async def remove_from_whitelist(ctx, user_id: str = None):
    """Remove a user from the moderation whitelist"""
    if not is_whitelisted(ctx.author.id):
        await ctx.send("❌ Access Denied.")
        return
    
    if not user_id:
        await ctx.send("❓ Usage: `!removemod 123456789012345678`")
        return
    
    user_id = user_id.replace("<@", "").replace(">", "").replace("!", "")
    
    if user_id not in WHITELISTED_USERS:
        await ctx.send(f"⚠️ User <@{user_id}> is not in the whitelist.")
        return
    
    if user_id == str(ctx.author.id) and len(WHITELISTED_USERS) <= 1:
        await ctx.send("❌ You cannot remove yourself if you're the only whitelisted user.")
        return
    
    WHITELISTED_USERS.remove(user_id)
    save_whitelist(WHITELISTED_USERS)
    
    await ctx.send(f"✅ User <@{user_id}> has been removed from the moderation whitelist.")

@bot.command(name="mods")
async def show_whitelist(ctx):
    """Show all whitelisted moderators"""
    if not is_whitelisted(ctx.author.id):
        await ctx.send("❌ Access Denied.")
        return
    
    if not WHITELISTED_USERS:
        await ctx.send("No users are whitelisted.")
        return
    
    embed = discord.Embed(
        title="🛡️ Moderator Whitelist",
        color=discord.Color.green()
    )
    
    user_list = []
    for uid in WHITELISTED_USERS:
        try:
            user = await bot.fetch_user(int(uid))
            user_list.append(f"{user.mention} (`{uid}`)")
        except:
            user_list.append(f"Unknown User (`{uid}`)")
    
    embed.add_field(name="Moderators", value="\n".join(user_list), inline=False)
    embed.set_footer(text=f"Total: {len(WHITELISTED_USERS)} moderators")
    
    await ctx.send(embed=embed)

# ============================================
# INFO COMMANDS
# ============================================

@bot.command(name="ping")
async def ping(ctx):
    """Check bot latency"""
    await ctx.send(f"🏓 Pong! Latency: {round(bot.latency * 1000)}ms")

@bot.command(name="serverinfo")
async def server_info(ctx):
    """Display server information"""
    guild = ctx.guild
    
    embed = discord.Embed(
        title=f"📊 Server Info - {guild.name}",
        color=discord.Color.blue(),
        timestamp=datetime.utcnow()
    )
    
    embed.add_field(name="Owner", value=guild.owner.mention, inline=True)
    embed.add_field(name="Members", value=guild.member_count, inline=True)
    embed.add_field(name="Channels", value=len(guild.channels), inline=True)
    embed.add_field(name="Roles", value=len(guild.roles), inline=True)
    embed.add_field(name="Boost Level", value=guild.premium_tier, inline=True)
    embed.add_field(name="Created", value=guild.created_at.strftime("%Y-%m-%d"), inline=True)
    
    await ctx.send(embed=embed)

@bot.command(name="helpmod")
async def help_command(ctx):
    """Show all moderation commands"""
    is_mod = is_whitelisted(ctx.author.id)
    
    embed = discord.Embed(
        title="🛡️ Moderation Bot v2.0",
        description="**Whitelist Protected** - Only approved moderators can use moderation commands.",
        color=discord.Color.blue()
    )
    
    embed.add_field(
        name="📋 Purge Commands",
        value="`!purge <amount>` - Delete X messages (with delay)\n"
              "`!purgeuser @User <amount>` - Delete user's messages\n"
              "`!purgebot <amount>` - Delete bot's messages\n"
              "`!setdelay <seconds>` - Set purge delay (0-30s)",
        inline=False
    )
    
    embed.add_field(
        name="🔒 Channel Control",
        value="`!slowmode <seconds>` - Set channel slowmode\n"
              "`!lock` - Lock current channel\n"
              "`!unlock` - Unlock current channel\n"
              "`!setlog #channel` - Set logging channel",
        inline=False
    )
    
    embed.add_field(
        name="⚠️ User Management",
        value="`!warn @User <reason>` - Warn a user\n"
              "`!warnings @User` - Check warnings\n"
              "`!clearwarns @User` - Clear warnings\n"
              "`!timeout @User <minutes>` - Timeout user\n"
              "`!kick @User <reason>` - Kick user\n"
              "`!ban @User <reason>` - Ban user",
        inline=False
    )
    
    embed.add_field(
        name="👥 Whitelist Management",
        value="`!mods` - List whitelisted moderators\n"
              "`!addmod <user_id>` - Add to whitelist\n"
              "`!removemod <user_id>` - Remove from whitelist",
        inline=False
    )
    
    embed.add_field(
        name="ℹ️ Info",
        value="`!ping` - Check latency\n"
              "`!serverinfo` - Server information\n"
              "`!helpmod` - Show this menu",
        inline=False
    )
    
    embed.set_footer(text=f"Purge Delay: {guild_settings.get(str(ctx.guild.id), {}).get('purge_delay', DEFAULT_DELAY)}s | Whitelisted: {len(WHITELISTED_USERS)}")
    
    await ctx.send(embed=embed)

# ============================================
# ERROR HANDLING
# ============================================

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("❓ Missing argument. Use `!helpmod` for command syntax.")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("❓ Invalid argument. Use `!helpmod` for command syntax.")
    elif isinstance(error, commands.CommandNotFound):
        pass
    else:
        await ctx.send(f"❌ Error: {str(error)}")

# ============================================
# RUN THE BOT
# ============================================

if __name__ == "__main__":
    if DISCORD_TOKEN == "YOUR_DISCORD_BOT_TOKEN_HERE":
        print("="*50)
        print("ERROR: Please add your Discord bot token to DISCORD_TOKEN!")
        print("Get one from: https://discord.com/developers/applications")
        print("="*50)
    else:
        print("Starting Moderation Bot v2.0...")
        bot.run(DISCORD_TOKEN)
