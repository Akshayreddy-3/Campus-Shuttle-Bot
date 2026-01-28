#!/usr/bin/env python3
"""
Campus Shuttle Bot for Telegram
A bot to check shuttle bus schedules at various campus locations.
"""

import json
import logging
import os
import pytz
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# Bot Token - uses environment variable for cloud, fallback for local
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8483816124:AAGSxAnKnRRcV-7_tjuZH0xqm98bOQRSvHs")

# Timezone for the campus (Houston is Central Time)
CAMPUS_TZ = pytz.timezone('US/Central')

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

# Get current time in campus timezone
def get_now():
    return datetime.now(CAMPUS_TZ)

# Get current day type
def get_day_type():
    now = get_now()
    day = now.weekday()  # 0=Monday, 6=Sunday
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

# Get current minutes since midnight in campus timezone
def get_current_minutes():
    now = get_now()
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
    trips = schedule.get('trips', [])
    if not schedule:
        return []
    
    times = []
    current_minutes = get_current_minutes()
    
    # Campus stops that trigger "Heading to" info
    campus_stops = ['recreation-center', 'hunter-hall', 'sscb', 'bayou-student']
    
    for i, trip in enumerate(trips):
        time_str = trip.get('times', {}).get(stop_id)
        if time_str and time_str != 'DROP OFF' and 'Grocery' not in time_str:
            minutes = parse_time(time_str)
            if minutes is not None:
                heading_to = None
                # If it's a campus stop, find where the bus goes next
                if stop_id in campus_stops:
                    # 1. Check the CURRENT trip for any remaining stops
                    found_in_current = False
                    times_dict = trip.get('times', {})
                    # Get all stops sorted by their defined order
                    sorted_stop_ids = sorted(shuttle_data['stops'].keys(), key=lambda x: shuttle_data['stops'][x]['order'])
                    
                    current_stop_order = shuttle_data['stops'][stop_id]['order']
                    for sid in sorted_stop_ids:
                        if shuttle_data['stops'][sid]['order'] > current_stop_order:
                            next_val = times_dict.get(sid)
                            if next_val == 'DROP OFF':
                                # User rule: DROP OFF after 8:30 PM means BAP&R
                                if minutes >= 20.5 * 60: # 8:30 PM
                                    heading_to = "Bay Area Park & Ride"
                                else:
                                    heading_to = "Bay Area Park & Ride (DROP OFF ONLY)"
                                found_in_current = True
                                break
                            elif next_val and (('AM' in next_val) or ('PM' in next_val)):
                                next_stop_name = shuttle_data['stops'].get(sid, {}).get('name', sid)
                                heading_to = f"{next_stop_name} ({next_val})"
                                found_in_current = True
                                break
                    
                    # 2. If not found in current trip, check the NEXT trip(s)
                    if not found_in_current:
                        for next_trip_idx in range(i + 1, len(trips)):
                            next_trip = trips[next_trip_idx]
                            next_times = next_trip.get('times', {})
                            
                            # Find the first stop in the next trip that has an entry
                            for next_stop_id, next_time_val in next_times.items():
                                if next_time_val == 'DROP OFF':
                                    heading_to = "Bay Area Park & Ride (DROP OFF ONLY)"
                                    break
                                elif next_time_val and (('AM' in next_time_val) or ('PM' in next_time_val)):
                                    next_stop_name = shuttle_data['stops'].get(next_stop_id, {}).get('name', next_stop_id)
                                    heading_to = f"{next_stop_name} ({next_time_val})"
                                    break
                            if heading_to: break
                
                diff = minutes - current_minutes
                times.append({
                    'time': time_str,
                    'minutes': minutes,
                    'is_past': diff < 0,
                    'eta': format_eta(diff),
                    'heading_to': heading_to
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

# Reminder callback
async def send_reminder(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    await context.bot.send_message(
        job.chat_id, 
        text=f"🔔 *Reminder!* Your shuttle at *{job.data['stop_name']}* departs in 5 minutes ({job.data['time']}). 🚌💨",
        parse_mode='Markdown'
    )

# Command Handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send welcome message"""
    now = get_now()
    hour = now.hour
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
        message += f"📅 Today's schedule: *{get_day_label()}*\n"
        message += f"🕒 Current time: *{now.strftime('%I:%M %p')}*\n\n"
        message += "I can help you check shuttle times and set reminders!\n\n"
        message += "*Commands:*\n"
        message += "/next - Find next shuttle at a stop\n"
        message += "/stops - See all stops\n"
        message += "/schedule - See full schedule for a stop\n"
        message += "/time - Check bot's current time\n"
        message += "/help - Show this help message\n\n"
        message += "Or just type a stop name like *Hunter Hall* or *Delta*!"
    
    await update.message.reply_text(message, parse_mode='Markdown')

async def time_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show current time in campus timezone"""
    now = get_now()
    message = f"🕒 *Current Campus Time:*\n"
    message += f"Date: {now.strftime('%A, %b %d, %Y')}\n"
    message += f"Time: {now.strftime('%I:%M:%S %p')}\n"
    message += f"Schedule Type: *{get_day_label()}*"
    
    await update.message.reply_text(message, parse_mode='Markdown')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send help message"""
    message = "🚌 *Shuttle Bot Help*\n\n"
    message += "*Commands:*\n"
    message += "/start - Welcome message\n"
    message += "/next - Find next shuttle at a stop\n"
    message += "/stops - See all available stops\n"
    message += "/schedule - See full schedule for a stop\n\n"
    message += "*Features:*\n"
    message += "🔔 *Reminders:* When viewing a schedule, tap the 🔔 button to get a notification 5 minutes before departure.\n\n"
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
    
    keyboard = []
    for i, t in enumerate(upcoming):
        star = "⭐" if i == 0 else ""
        heading = f"\n    ↳ ➡️ _Heading to: {t['heading_to']}_" if t.get('heading_to') else ""
        message += f"{'➡️' if i==0 else '    '} *{t['time']}* - {t['eta']} {star}{heading}\n"
        # Add reminder button for the very next one
        if i == 0:
            keyboard.append([InlineKeyboardButton(f"🔔 Remind me 5m before {t['time']}", callback_data=f"remind_{stop['id']}_{t['time']}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
    await update.message.reply_text(message, reply_markup=reply_markup, parse_mode='Markdown')

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
    keyboard = []
    
    for t in times:
        heading = f"\n    ↳ ➡️ _Heading to: {t['heading_to']}_" if t.get('heading_to') else ""
        if t['is_past']:
            message += f"~~{t['time']}~~ _(passed)_{heading}\n"
        elif not found_next:
            message += f"➡️ *{t['time']}* - {t['eta']} ⭐{heading}\n"
            found_next = True
            # Add reminder button for the next one
            keyboard.append([InlineKeyboardButton(f"🔔 Remind me 5m before {t['time']}", callback_data=f"remind_{stop['id']}_{t['time']}")])
        else:
            message += f"    {t['time']} - {t['eta']}{heading}\n"
    
    reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
    
    if is_callback:
        await update_or_query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update_or_query.message.reply_text(message, reply_markup=reply_markup, parse_mode='Markdown')

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
    
    elif data.startswith('remind_'):
        # Format: remind_stopid_time
        parts = data.split('_')
        stop_id = parts[1]
        time_str = parts[2]
        
        stop_name = shuttle_data['stops'][stop_id]['name']
        minutes = parse_time(time_str)
        now_minutes = get_current_minutes()
        
        # Calculate delay (minutes until 5m before departure)
        remind_at = minutes - 5
        delay_seconds = (remind_at - now_minutes) * 60
        
        if delay_seconds < 0:
            await query.message.reply_text("⚠️ This shuttle is departing too soon (in less than 5 minutes) to set a reminder!")
            return
            
        # Schedule the job
        context.job_queue.run_once(
            send_reminder, 
            delay_seconds, 
            chat_id=query.message.chat_id, 
            name=f"remind_{query.message.chat_id}_{stop_id}_{minutes}",
            data={'stop_name': stop_name, 'time': time_str}
        )
        
        await query.message.reply_text(f"✅ *Reminder set!* I'll notify you 5 minutes before the {time_str} shuttle at {stop_name}.", parse_mode='Markdown')

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
    application.add_handler(CommandHandler("time", time_command))
    application.add_handler(CallbackQueryHandler(handle_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Start polling
    print("✅ Bot is running! Press Ctrl+C to stop.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()

