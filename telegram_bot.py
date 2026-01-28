#!/usr/bin/env python3
"""
Campus Shuttle Bot for Telegram
A bot to check shuttle bus schedules at various campus locations.
"""

import json
import logging
import os
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# Bot Token - uses environment variable for cloud, fallback for local
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8483816124:AAGSxAnKnRRcV-7_tjuZH0xqm98bOQRSvHs")

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Load shuttle schedule
def load_schedule():
    try:
        with open('shuttle-schedule.json', 'r') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading schedule: {e}")
        return None

shuttle_data = load_schedule()

# Get current day type
def get_day_type():
    day = datetime.now().weekday()  # 0=Monday, 6=Sunday
    if day == 6:  # Sunday
        return None
    elif day == 5:  # Saturday
        return 'sat'
    elif day == 4:  # Friday
        return 'fri'
    else:  # Mon-Thu
        return 'mon-thu'

def get_day_label():
    day_type = get_day_type()
    if not day_type:
        return "Sunday (No Service)"
    if shuttle_data and day_type in shuttle_data.get('schedule', {}):
        return shuttle_data['schedule'][day_type].get('dayLabel', day_type)
    return day_type

# Parse time string to minutes
def parse_time(time_str):
    if not time_str or time_str == 'DROP OFF' or 'Grocery' in time_str:
        return None
    try:
        # Parse "6:20 AM" format
        time_obj = datetime.strptime(time_str.strip(), '%I:%M %p')
        return time_obj.hour * 60 + time_obj.minute
    except:
        return None

# Get current minutes since midnight
def get_current_minutes():
    now = datetime.now()
    return now.hour * 60 + now.minute

# Format minutes to readable time
def format_eta(minutes_diff):
    if minutes_diff < 0:
        return "Passed"
    elif minutes_diff == 0:
        return "Now! 🚌"
    elif minutes_diff < 60:
        return f"in {minutes_diff} min"
    else:
        hours = minutes_diff // 60
        mins = minutes_diff % 60
        return f"in {hours}h {mins}m"

# Find stop by query
def find_stop(query):
    if not shuttle_data:
        return None
    
    query = query.lower().strip()
    
    # Direct match
    for stop_id, stop_info in shuttle_data.get('stops', {}).items():
        stop_name = stop_info['name'].lower()
        if query in stop_name or stop_name in query:
            return {'id': stop_id, **stop_info}
    
    # Keyword matching
    keywords = {
        'hunter': 'hunter-hall',
        'hall': 'hunter-hall',
        'sscb': 'sscb',
        'bayou': 'bayou-student',
        'student': 'bayou-student',
        'rec': 'recreation-center',
        'recreation': 'recreation-center',
        'delta': 'delta',
        'arbor': 'arbor',
        'forest': 'university-forest',
        'university': 'university-forest',
        'apt': 'university-forest',
        'apartment': 'university-forest',
        'fitness': 'anytime-fitness',
        'anytime': 'anytime-fitness',
        'gym': 'anytime-fitness',
        'bay': 'bay-area-park-ride',
        'park': 'bay-area-park-ride',
        'ride': 'bay-area-park-ride',
        'united': 'united-way',
        'way': 'united-way',
        'coastal': 'coastal-flow',
        'police': 'police-building'
    }
    
    for keyword, stop_id in keywords.items():
        if keyword in query:
            if stop_id in shuttle_data.get('stops', {}):
                return {'id': stop_id, **shuttle_data['stops'][stop_id]}
    
    return None

# Get schedule for a stop
def get_stop_schedule(stop_id):
    day_type = get_day_type()
    if not day_type or not shuttle_data:
        return []
    
    schedule = shuttle_data.get('schedule', {}).get(day_type, {})
    if not schedule:
        return []
    
    times = []
    current_minutes = get_current_minutes()
    
    for trip in schedule.get('trips', []):
        time_str = trip.get('times', {}).get(stop_id)
        if time_str and time_str != 'DROP OFF' and 'Grocery' not in time_str:
            minutes = parse_time(time_str)
            if minutes is not None:
                diff = minutes - current_minutes
                times.append({
                    'time': time_str,
                    'minutes': minutes,
                    'is_past': diff < 0,
                    'eta': format_eta(diff)
                })
    
    return sorted(times, key=lambda x: x['minutes'])

# Get next shuttle at a stop
def get_next_shuttle(stop_id):
    times = get_stop_schedule(stop_id)
    current_minutes = get_current_minutes()
    
    for t in times:
        if t['minutes'] >= current_minutes:
            return t
    return None

# Command Handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send welcome message"""
    hour = datetime.now().hour
    if hour < 12:
        greeting = "Good morning"
    elif hour < 17:
        greeting = "Good afternoon"
    else:
        greeting = "Good evening"
    
    day_type = get_day_type()
    
    message = f"{greeting}! 🚌 I'm your *Campus Shuttle Bot*.\n\n"
    
    if not day_type:
        message += "⚠️ *Note:* Today is Sunday. The shuttle service doesn't operate on Sundays."
    else:
        message += f"📅 Today's schedule: *{get_day_label()}*\n\n"
        message += "I can help you check shuttle times!\n\n"
        message += "*Commands:*\n"
        message += "/next - Find next shuttle at a stop\n"
        message += "/stops - See all stops\n"
        message += "/schedule - See full schedule for a stop\n"
        message += "/help - Show this help message\n\n"
        message += "Or just type a stop name like *Hunter Hall* or *Delta*!"
    
    await update.message.reply_text(message, parse_mode='Markdown')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send help message"""
    message = "🚌 *Shuttle Bot Help*\n\n"
    message += "*Commands:*\n"
    message += "/start - Welcome message\n"
    message += "/next - Find next shuttle at a stop\n"
    message += "/stops - See all available stops\n"
    message += "/schedule - See full schedule for a stop\n\n"
    message += "*Quick Tips:*\n"
    message += "• Just type a stop name to see its schedule\n"
    message += "• Type 'next hunter hall' for next shuttle\n"
    message += "• Use short names like 'rec', 'delta', 'sscb'\n"
    
    await update.message.reply_text(message, parse_mode='Markdown')

async def stops_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show all stops as inline buttons"""
    if not shuttle_data:
        await update.message.reply_text("❌ Schedule data not available.")
        return
    
    keyboard = []
    stops = shuttle_data.get('stops', {})
    sorted_stops = sorted(stops.items(), key=lambda x: x[1].get('order', 0))
    
    # Create buttons in pairs
    row = []
    for stop_id, stop_info in sorted_stops:
        emoji = "🏛️" if stop_info.get('type') == 'on-campus' else "🏠"
        btn = InlineKeyboardButton(
            f"{emoji} {stop_info['name'][:20]}",
            callback_data=f"schedule_{stop_id}"
        )
        row.append(btn)
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message = "📍 *All Shuttle Stops*\n\n"
    message += "🏛️ = On Campus | 🏠 = Off Campus\n\n"
    message += "Tap any stop to see its schedule:"
    
    await update.message.reply_text(message, reply_markup=reply_markup, parse_mode='Markdown')

async def next_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show next shuttle - if stop provided, show for that stop"""
    day_type = get_day_type()
    if not day_type:
        await update.message.reply_text("⚠️ No shuttle service on Sundays!")
        return
    
    # Check if a stop was specified
    if context.args:
        query = ' '.join(context.args)
        stop = find_stop(query)
        if stop:
            await send_next_shuttle(update, stop)
            return
    
    # Show stop selection
    await stops_command(update, context)

async def schedule_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show full schedule for a stop"""
    day_type = get_day_type()
    if not day_type:
        await update.message.reply_text("⚠️ No shuttle service on Sundays!")
        return
    
    if context.args:
        query = ' '.join(context.args)
        stop = find_stop(query)
        if stop:
            await send_schedule(update, stop)
            return
    
    await stops_command(update, context)

async def send_next_shuttle(update: Update, stop: dict):
    """Send next shuttle info for a stop"""
    next_shuttle = get_next_shuttle(stop['id'])
    
    if not next_shuttle:
        message = f"😔 No more shuttles at *{stop['name']}* for today.\n"
        message += "The last shuttle has already passed."
        await update.message.reply_text(message, parse_mode='Markdown')
        return
    
    # Get next 3 shuttles
    all_times = get_stop_schedule(stop['id'])
    current_minutes = get_current_minutes()
    upcoming = [t for t in all_times if t['minutes'] >= current_minutes][:3]
    
    message = f"🚌 *Next shuttles at {stop['name']}*\n"
    message += f"📅 {get_day_label()}\n\n"
    
    for i, t in enumerate(upcoming):
        if i == 0:
            message += f"➡️ *{t['time']}* - {t['eta']} ⭐\n"
        else:
            message += f"    {t['time']} - {t['eta']}\n"
    
    await update.message.reply_text(message, parse_mode='Markdown')

async def send_schedule(update_or_query, stop: dict, is_callback=False):
    """Send full schedule for a stop"""
    times = get_stop_schedule(stop['id'])
    
    if not times:
        message = f"😔 No scheduled stops at *{stop['name']}* for today ({get_day_label()})."
        if is_callback:
            await update_or_query.edit_message_text(message, parse_mode='Markdown')
        else:
            await update_or_query.message.reply_text(message, parse_mode='Markdown')
        return
    
    message = f"📅 *{stop['name']}*\n"
    message += f"Schedule for {get_day_label()}\n\n"
    
    current_minutes = get_current_minutes()
    found_next = False
    
    for t in times:
        if t['is_past']:
            message += f"~~{t['time']}~~ _(passed)_\n"
        elif not found_next:
            message += f"➡️ *{t['time']}* - {t['eta']} ⭐\n"
            found_next = True
        else:
            message += f"    {t['time']} - {t['eta']}\n"
    
    if is_callback:
        await update_or_query.edit_message_text(message, parse_mode='Markdown')
    else:
        await update_or_query.message.reply_text(message, parse_mode='Markdown')

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button callbacks"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    if data.startswith('schedule_'):
        stop_id = data.replace('schedule_', '')
        if shuttle_data and stop_id in shuttle_data.get('stops', {}):
            stop = {'id': stop_id, **shuttle_data['stops'][stop_id]}
            await send_schedule(query, stop, is_callback=True)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle regular text messages"""
    text = update.message.text.lower().strip()
    
    day_type = get_day_type()
    if not day_type:
        await update.message.reply_text("⚠️ No shuttle service on Sundays! Check back Monday.")
        return
    
    # Check for "next" keyword
    if 'next' in text or 'when' in text:
        stop = find_stop(text)
        if stop:
            await send_next_shuttle(update, stop)
            return
    
    # Try to find a stop in the message
    stop = find_stop(text)
    if stop:
        await send_schedule(update, stop)
        return
    
    # Unknown query
    message = "🤔 I didn't understand that.\n\n"
    message += "Try:\n"
    message += "• Type a stop name: *Hunter Hall*\n"
    message += "• Ask for next shuttle: *next delta*\n"
    message += "• Use /stops to see all locations"
    
    await update.message.reply_text(message, parse_mode='Markdown')

def main():
    """Start the bot"""
    print("🚌 Starting Campus Shuttle Bot...")
    
    # Create application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("stops", stops_command))
    application.add_handler(CommandHandler("next", next_command))
    application.add_handler(CommandHandler("schedule", schedule_command))
    application.add_handler(CallbackQueryHandler(handle_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Start polling
    print("✅ Bot is running! Press Ctrl+C to stop.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
