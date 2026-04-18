import json
import os
from pathlib import Path
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

import time

INTERVALS = [
    10 * 60,           
    3 * 60 * 60,       
    24 * 60 * 60,     
    3 * 24 * 60 * 60,  
    7 * 24 * 60 * 60,  
    30 * 24 * 60 * 60  
]

TOKEN = os.getenv("TOKEN")
DATA_FILE = Path("data.json")



def load_data():
    if DATA_FILE.exists():
        return json.loads(DATA_FILE.read_text())
    return {}


def save_data(data):
    DATA_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2))


data = load_data()


def get_user(user_id):
    user_id = str(user_id)
    if user_id not in data:
        data[user_id] = {"blocks": {}}
    return data[user_id]



async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! 👋\n"
        "Я бот для заучивания слов.\n\n"
        "/add - добавить слово\n"
        "/blocks - посмотреть блоки\n"
        "/study - учить слова"
    )


async def blocks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_user.id)
    blocks = user["blocks"]

    if not blocks:
        await update.message.reply_text("Блоков пока нет.")
        return

    text = "📦 Твои блоки:\n\n"
    for name, words in blocks.items():
        text += f"• {name} — {len(words)} слов\n"

    await update.message.reply_text(text)


async def add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["adding_word"] = True
    await update.message.reply_text(
        "Введи слово и перевод через дефис:\n"
        "apple - яблоко"
    )

async def study(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)

    if not user["blocks"]:
        await update.message.reply_text("У тебя пока нет блоков 😔")
        return

    keyboard = [[block] for block in user["blocks"].keys()]

    await update.message.reply_text(
        "Выбери блок для изучения:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )

    context.user_data["choosing_study_block"] = True


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)
    text = update.message.text.strip()

    if context.user_data.get("choosing_study_block"):
        block = text

        if block not in user["blocks"]:
            await update.message.reply_text("Выбери блок кнопкой.")
            return

        now = int(time.time())

        words = user["blocks"][block]
        due_words = [w for w in words if w["next_review"] <= now]

        if not due_words:
            await update.message.reply_text("😴 Пока нет слов для повторения")
            return

        context.user_data.clear()
        context.user_data["study_block"] = block
        context.user_data["study_words"] = due_words
        context.user_data["study_index"] = 0

        word = due_words[0]
        context.user_data["current_word"] = word
        context.user_data["awaiting_answer"] = True

        await update.message.reply_text(
            f"Как переводится слово:\n\n👉 {word['word']}"
        )
        return
        

    if context.user_data.get("awaiting_answer"):
        word = context.user_data["current_word"]
        correct = word["translation"].lower().strip()
        answer = text.lower().strip()

        now = int(time.time())

        if answer == correct:
            await update.message.reply_text("✅ Правильно!")
            word["stage"] = min(word["stage"] + 1, len(INTERVALS) - 1)
        else:
            await update.message.reply_text(
            f"❌ Неправильно\nПравильный ответ: {word['translation']}"
            )
            word["stage"] = max(0, word["stage"] - 1)

        word["next_review"] = now + INTERVALS[word["stage"]]

        save_data(data)

        block = context.user_data["study_block"]
        index = context.user_data["study_index"] + 1
        words = context.user_data["study_words"]

        if index >= len(words):
            context.user_data.clear()
            await update.message.reply_text("🎉 Блок завершён!")
            return

        context.user_data["study_index"] = index
        next_word = words[index]
        context.user_data["current_word"] = next_word

        await update.message.reply_text(
            f"Следующее слово:\n\n👉 {next_word['word']}"
        )
        return

    if context.user_data.get("creating_block"):
        block_name = text

        if block_name in user["blocks"]:
            await update.message.reply_text("Такой блок уже есть.")
            return

        user["blocks"][block_name] = [context.user_data["new_word"]]
        save_data(data)

        context.user_data.clear()
        await update.message.reply_text(f"Блок «{block_name}» создан ✅")
        return

    if context.user_data.get("adding_word"):
        if "-" not in text:
            await update.message.reply_text("Используй формат: слово - перевод")
            return

        word, translation = map(str.strip, text.split("-", 1))

        context.user_data["new_word"] = {
            "word": word,
            "translation": translation,
            "stage": 0,
            "next_review": 0
        }

        context.user_data["adding_word"] = False

        blocks = list(user["blocks"].keys())
        keyboard = [[b] for b in blocks]
        keyboard.append(["➕ Новый блок"])

        await update.message.reply_text(
            "Выбери блок:",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return



    if "new_word" in context.user_data:
        if text == "➕ Новый блок":
            context.user_data["creating_block"] = True
            await update.message.reply_text("Введи название нового блока:")
            return

        if text not in user["blocks"]:
            await update.message.reply_text("Выбери блок кнопкой.")
            return

        user["blocks"][text].append(context.user_data["new_word"])
        save_data(data)

        del context.user_data["new_word"]
        await update.message.reply_text("Слово добавлено ✅")
        return

    if context.user_data.get("creating_block"):
        block_name = text

        if block_name in user["blocks"]:
            await update.message.reply_text("Такой блок уже есть.")
            return

        user["blocks"][block_name] = [context.user_data["new_word"]]
        save_data(data)

        context.user_data.clear()
        await update.message.reply_text(f"Блок «{block_name}» создан ✅")
        return



def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add", add))
    app.add_handler(CommandHandler("blocks", blocks))
    app.add_handler(CommandHandler("study", study))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Бот запущен")
    app.run_polling()


if __name__ == "__main__":
    main()
