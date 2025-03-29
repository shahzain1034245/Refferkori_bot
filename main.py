import logging
import sqlite3
import os
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart, Command
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")
DB_PATH = os.getenv("DB_PATH", "referrals.db")

if not BOT_TOKEN or not CHANNEL_ID:
    logging.error("BOT_TOKEN or CHANNEL_ID is not set. Check your environment variables.")
    exit(1)

# Initialize bot and dispatcher
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Database setup
def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def initialize_database():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY, 
                user_id INTEGER UNIQUE, 
                referrer_id INTEGER, 
                balance INTEGER DEFAULT 0
            )
        """)
        conn.commit()

initialize_database()

# Check if user is subscribed
async def check_subscription(user_id):
    try:
        chat_member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return chat_member.status in ["member", "administrator", "creator"]
    except Exception as e:
        logging.warning(f"Subscription check failed for {user_id}: {e}")
        return False

# Start command
@dp.message(CommandStart())
async def start(message: types.Message):
    user_id = message.from_user.id
    args = message.text.split()
    referrer_id = int(args[1]) if len(args) > 1 and args[1].isdigit() else None

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
        user = cursor.fetchone()

        if not user:
            cursor.execute("INSERT INTO users (user_id, referrer_id) VALUES (?, ?)", (user_id, referrer_id))
            conn.commit()
            if referrer_id:
                cursor.execute("UPDATE users SET balance = balance + 2 WHERE user_id=?", (referrer_id,))
                conn.commit()

    referral_link = f"https://t.me/MyAwesomeBot?start={user_id}"  # Replace with your bot's username
    markup = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Invite & Earn 💰", url=referral_link)]]
    )
    await message.answer(f"👋 Welcome! Earn money by inviting friends.\n\nYour Referral Link:\n{referral_link}", reply_markup=markup)

# Check balance
@dp.message(Command("balance"))
async def balance(message: types.Message):
    user_id = message.from_user.id
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT balance FROM users WHERE user_id=?", (user_id,))
        balance = cursor.fetchone()
    
    await message.answer(f"💰 Your balance: {balance['balance'] if balance else 0} Taka")

# Withdraw earnings
@dp.message(Command("withdraw"))
async def withdraw(message: types.Message):
    user_id = message.from_user.id
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT balance FROM users WHERE user_id=?", (user_id,))
        balance = cursor.fetchone()

        if balance and balance["balance"] >= 100:
            await message.answer("✅ Withdrawal request sent! Admin will process your payment soon.")
            cursor.execute("UPDATE users SET balance = balance - 100 WHERE user_id=?", (user_id,))
            conn.commit()
        else:
            await message.answer("❌ You need at least 100 Taka to withdraw.")

# Leaderboard
@dp.message(Command("leaderboard"))
async def leaderboard(message: types.Message):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, balance FROM users ORDER BY balance DESC LIMIT 10")
        top_users = cursor.fetchall()
    
    leaderboard_text = "🏆 Top Earners:\n"
    for rank, user in enumerate(top_users, start=1):
        leaderboard_text += f"{rank}. User {user['user_id']} - {user['balance']} Taka\n"

    await message.answer(leaderboard_text)

# Run the bot
async def main():
    logging.basicConfig(level=logging.INFO)
    try:
        await dp.start_polling(bot, skip_updates=True)
    except Exception as e:
        logging.error(f"Error running the bot: {e}")

if __name__ == "__main__":
    asyncio.run(main())
