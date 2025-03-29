import os
import logging
from datetime import datetime, timezone
from telegram import Update, Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler
import psycopg2
import secrets

logging.basicConfig(level=logging.INFO)

def get_db_connection():
    return psycopg2.connect(os.environ['DATABASE_URL'])

def create_tables(conn):
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                referral_code TEXT UNIQUE,
                balance NUMERIC DEFAULT 0,
                last_bonus_claim TIMESTAMPTZ
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS referrals (
                id SERIAL PRIMARY KEY,
                new_user_id INTEGER,
                referrer_id INTEGER,
                timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (new_user_id)
            )
        """)
    conn.commit()

def generate_referral_code(conn):
    while True:
        code = secrets.token_hex(3)  # Adjust length as needed
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM users WHERE referral_code = %s", (code, ))
            if not cur.fetchone():
                return code

def add_user(conn, user_id, username):
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM users WHERE user_id = %s", (user_id, ))
        if not cur.fetchone():
            referral_code = generate_referral_code(conn)
            cur.execute("INSERT INTO users (user_id, username, referral_code) VALUES (%s, %s, %s)", (user_id, username, referral_code))
            conn.commit()
            return referral_code
    return None

def record_referral(conn, new_user_id, referrer_id):
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM referrals WHERE new_user_id = %s", (new_user_id, ))
        if not cur.fetchone():
            cur.execute("INSERT INTO referrals (new_user_id, referrer_id) VALUES (%s, %s)", (new_user_id, referrer_id))
            conn.commit()

async def is_in_channel(bot, user_id, channel_id):
    try:
        member = await bot.get_chat_member(chat_id=channel_id, user_id=user_id)
        return member.status in ['member', 'owner']
    except:
        return False

async def start(update: Update, context):
    user_id = update.effective_user.id
    username = update.effective_user.username
    conn = get_db_connection()
    create_tables(conn)
    
    # Check if user is already registered
    with conn.cursor() as cur:
        cur.execute("SELECT user_id FROM users WHERE user_id = %s", (user_id, ))
        row = cur.fetchone()
        if not row:
            # New user
            args = update.message.text.split()[1:]
            if args:
                referral_code = args[0]
                cur.execute("SELECT user_id FROM users WHERE referral_code = %s", (referral_code, ))
                referrer_row = cur.fetchone()
                if referrer_row:
                    referrer_id = referrer_row[0]
                    if user_id != referrer_id:
                        record_referral(conn, new_user_id=user_id, referrer_id=referrer_id)
                        await update.message.reply_text("Thank you for using the referral link!")
                    else:
                        await update.message.reply_text("You cannot refer yourself.")
                else:
                    await update.message.reply_text("Invalid referral code.")
            # Add user to database
            referral_code = generate_referral_code(conn)
            cur.execute("INSERT INTO users (user_id, username, referral_code) VALUES (%s, %s, %s)", (user_id, username, referral_code))
            conn.commit()
            await update.message.reply_text(f"Welcome! Your referral code is {referral_code}.")
        else:
            await update.message.reply_text("Welcome back!")
    
    # Check if user is in the channel
    channel_id = int(os.environ.get('CHAN_ID'))
    if not await is_in_channel(bot=context.bot, user_id=user_id, channel_id=channel_id):
        await update.message.reply_text("Please join our channel to use the bot features.")
        # Provide button to join channel
        channel_link = f"https://t.me/{channel_username}"
        keyboard = [[InlineKeyboardButton("Join Channel", url=channel_link)]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Click here to join our channel.", reply_markup=reply_markup)
    else:
        # Show main menu
        main_menu_buttons = [
            [InlineKeyboardButton("Balance", callback_data="balance"),
             InlineKeyboardButton("Referral Info", callback_data="referral_info")],
            [InlineKeyboardButton("Withdraw", callback_data="withdraw"),
             InlineKeyboardButton("Earning Guide", callback_data="earning_guide")]
        ]
        main_menu_markup = InlineKeyboardMarkup(main_menu_buttons)
        await update.message.reply_text("Welcome to the bot! Please select an option:", reply_markup=main_menu_markup)

async def callback_query_handler(update: Update, context):
    query = update.callback_query
    data = query.data
    user_id = query.from_user.id
    conn = get_db_connection()
    
    if data == "balance":
        with conn.cursor() as cur:
            cur.execute("SELECT balance FROM users WHERE user_id = %s", (user_id, ))
            row = cur.fetchone()
            if row:
                balance = row[0]
                await query.answer()
                message = f"Your current balance is ₹{balance}."
                back_button = [[InlineKeyboardButton("Back to Main Menu", callback_data="main_menu")]]
                back_markup = InlineKeyboardMarkup(back_button)
                await query.edit_message_text(message, reply_markup=back_markup)
            else:
                await query.answer("User not found.")
    
    elif data == "referral_info":
        with conn.cursor() as cur:
            cur.execute("SELECT referral_code FROM users WHERE user_id = %s", (user_id, ))
            row = cur.fetchone()
            if row:
                referral_code = row[0]
                referral_link = f"https://t.me/{os.environ.get('BOT_USERNAME')}?start={referral_code}"
                cur.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id = %s", (user_id, ))
                count = cur.fetchone()[0]
                message = f"Your referral link is: {referral_link}\nNumber of referrals: {count}"
                await query.answer()
                back_button = [[InlineKeyboardButton("Back to Main Menu", callback_data="main_menu")]]
                back_markup = InlineKeyboardMarkup(back_button)
                await query.edit_message_text(message, reply_markup=back_markup)
            else:
                await query.answer("User not found.")
    
    elif data == "withdraw":
        with conn.cursor() as cur:
            cur.execute("SELECT balance FROM users WHERE user_id = %s", (user_id, ))
            row = cur.fetchone()
            if row:
                balance = row[0]
                if balance >= 100:
                    confirm_buttons = [
                        [InlineKeyboardButton("Withdraw Now", callback_data="confirm_withdraw"),
                         InlineKeyboardButton("Cancel", callback_data="cancel_withdraw")]
                    ]
                    confirm_markup = InlineKeyboardMarkup(confirm_buttons)
                    await query.answer()
                    await query.edit_message_text(f"You have ₹{balance}. Are you sure you want to withdraw?", reply_markup=confirm_markup)
                else:
                    await query.answer()
                    await query.edit_message_text("Insufficient balance to withdraw (minimum 100 taka required).")
            else:
                await query.answer("User not found.")
    
    elif data == "earning_guide":
        guide_message = "You can earn by referring friends. Each successful referral gives you 2 taka. You can also claim a daily bonus of ₹1 if eligible."
        await query.answer()
        back_button = [[InlineKeyboardButton("Back to Main Menu", callback_data="main_menu")]]
        back_markup = InlineKeyboardMarkup(back_button)
        await query.edit_message_text(guide_message, reply_markup=back_markup)
    
    elif data == "main_menu":
        main_menu_buttons = [
            [InlineKeyboardButton("Balance", callback_data="balance"),
             InlineKeyboardButton("Referral Info", callback_data="referral_info")],
            [InlineKeyboardButton("Withdraw", callback_data="withdraw"),
             InlineKeyboardButton("Earning Guide", callback_data="earning_guide")]
        ]
        main_menu_markup = InlineKeyboardMarkup(main_menu_buttons)
        await query.answer()
        await query.edit_message_text("Welcome to the bot! Please select an option:", reply_markup=main_menu_markup)
    
    elif data == "confirm_withdraw":
        with conn.cursor() as cur:
            cur.execute("SELECT balance FROM users WHERE user_id = %s", (user_id, ))
            row = cur.fetchone()
            if row and row[0] >= 100:
                cur.execute("UPDATE users SET balance = 0 WHERE user_id = %s", (user_id, ))
                conn.commit()
                await query.answer()
                message = "Withdrawal successful. Your new balance is 0 taka."
                back_button = [[InlineKeyboardButton("Back to Main Menu", callback_data="main_menu")]]
                back_markup = InlineKeyboardMarkup(back_button)
                await query.edit_message_text(message, reply_markup=back_markup)
            else:
                await query.answer("Insufficient balance.")
    
    elif data == "cancel_withdraw":
        await query.answer()
        main_menu_buttons = [
            [InlineKeyboardButton("Balance", callback_data="balance"),
             InlineKeyboardButton("Referral Info", callback_data="referral_info")],
            [InlineKeyboardButton("Withdraw", callback_data="withdraw"),
             InlineKeyboardButton("Earning Guide", callback_data="earning_guide")]
        ]
        main_menu_markup = InlineKeyboardMarkup(main_menu_buttons)
        await query.edit_message_text("Withdrawal cancelled.", reply_markup=main_menu_markup)
    
    conn.close()

import asyncio

async def main():
    application = ApplicationBuilder().token(os.environ['BOT_TOKEN']).build()
    # Add handlers...
    RENDER_HOSTNAME = os.environ.get('RENDER_HOSTNAME')
    if RENDER_HOSTNAME:
        webHookUrl = f"https://{RENDER_HOSTNAME}/"
        await application.bot.set_webhook(url=webHookUrl)
        await application.run_webhook(listen="0.0.0.0", port=10000, url_path="")
    else:
        await application.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
