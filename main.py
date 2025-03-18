import logging
import telebot
from telebot import types
import pymysql.cursors
import math
import random

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', filename='bot.log')
user_state = {}  # {chat_id: {"topic_id": int, "questions": list, "current": int, "correct": int, "wrong": int}}

try:
    def connect_to_db():
        return pymysql.connect(
            host="localhost",
            user="root",
            password="2421Oleg",
            database="nmt_bot_db",
            cursorclass=pymysql.cursors.DictCursor,
            charset='utf8mb4'
        )
except Exception as e:
    logging.error(f"Error connecting to the database: {e}")

bot = telebot.TeleBot('6622496968:AAGF2eMIoTSow4Jj7g1XdktqTCG_rZ419b8')

@bot.message_handler(commands=['test'])
def test(message):
    pass

@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(message.chat.id, "Привіт, я чат-бот для підготовки до НМТ з історії України.\nЯкщо ти готовий, напиши /quiz")

@bot.message_handler(commands=['weekstats'])
def weekstats(message):
    connection = connect_to_db()

    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM results WHERE date >= NOW() - INTERVAL 6 DAY AND chat_id = %s", (message.chat.id,))
        tests = cursor.fetchall()

        total_correct = 0
        total_answers = 0
        topic_stats = set()

        for test in tests:
            topic_id = test['topic_id']
            correct = test['correct_answers']
            incorrect = test['incorrect_answers']
            total_correct += correct
            total_answers += correct + incorrect

            if topic_id is not None:
                cursor.execute("SELECT name FROM topics WHERE id = %s", (topic_id,))
                row = cursor.fetchone()
                topic_name = row['name'] if row else "Невідома тема"
                topic_stats.add(topic_name)

        if total_answers > 0:
            avg_percentage = (total_correct / total_answers) * 100
            topics_list = "\n".join([f"- {name}" for name in topic_stats]) if topic_stats else "Немає конкретних тем."

            bot.send_message(
                message.chat.id,
                f"📊 <b>Статистика за останній тиждень</b>\n\n"
                f"📌 <b>Теми:</b> \n{topics_list}\n"
                f"\n✅ <b>Середній відсоток правильних відповідей: {avg_percentage:.1f}%</b>",
                parse_mode="HTML"
            )
        else:
            bot.send_message(message.chat.id, "Немає відповідей для підрахунку.")


@bot.message_handler(commands=['quiz'])
def quiz_type_choice(message):
    choice_keyboard = types.InlineKeyboardMarkup(row_width=1)
    bytheme_btn = types.InlineKeyboardButton(text="По темах", callback_data="bytheme_choice")
    bycourse_btn = types.InlineKeyboardButton(text="По курсу", callback_data="bycourse_choice")
    choice_keyboard.add(bytheme_btn, bycourse_btn)
    bot.send_message(message.chat.id, "Обери вид тестування.\nПо темах - запитання по датах з вибраної теми.\nПо курсу - по одній даті з кожної теми у випадковому порядку.", reply_markup=choice_keyboard)

def get_total_topics():
    connection = connect_to_db()
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM topics")
        return cursor.fetchall()

def get_topics(page, limit):
    connection = connect_to_db()
    with connection.cursor() as cursor:
        offset = (page - 1) * limit
        cursor.execute(f"SELECT * FROM topics LIMIT %s OFFSET %s", (limit, offset))
        return cursor.fetchall()

def start_quiz_course(chat_id):
    connection = connect_to_db()
    with connection.cursor() as cursor:
        # Отримати всі унікальні теми
        cursor.execute("SELECT DISTINCT topic_id FROM dates")
        topics = cursor.fetchall()
        random.shuffle(topics)

    if not topics:
        bot.send_message(chat_id, "На жаль, питань немає.")
        return

    questions = []

    for topic in topics:
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM dates WHERE topic_id = %s ORDER BY RAND() LIMIT 1", (topic['topic_id'],))
            question = cursor.fetchone()
            if question:
                questions.append(question)

    user_state[chat_id] = {
        "by_topic": False,
        "topic_id": None,
        "topic_name": None, 
        "questions": questions,
        "current": 0,
        "correct": 0,
        "wrong": 0
    }

    send_question(chat_id, None)

def start_quiz_topic(topic_id, chat_id, topic_name):
    connection = connect_to_db()
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM dates WHERE topic_id = %s", (topic_id,))
        dates = cursor.fetchall()
        random.shuffle(dates)

    if not dates:
        bot.send_message(chat_id, "На жаль, питань для цієї теми немає.")
        return

    user_state[chat_id] = {
        "by_topic": True,
        "topic_id": topic_id,
        "topic_name": topic_name, 
        "questions": dates,
        "current": 0,
        "correct": 0,
        "wrong": 0
    }

    send_question(chat_id, topic_name)

def send_question(chat_id, topic_name):
    if user_state[chat_id]["by_topic"] == True:

        connection = connect_to_db()
        state = user_state.get(chat_id)
        
        if state is None or state["current"] >= len(state["questions"]):
            bot.send_message(chat_id, f'🔹 Тест по темі "{topic_name}" завершено!\n'
                                    f"✅ Правильних відповідей: {state['correct']}\n"
                                    f"❌ Неправильних відповідей: {state['wrong']}")
            
            with connection.cursor() as cursor:
                cursor.execute(f'INSERT INTO results (is_bytheme, chat_id, topic_id, correct_answers, incorrect_answers) VALUES ({True}, {chat_id}, {state["topic_id"]}, {state["correct"]}, {state["wrong"]})')
                connection.commit()

            del user_state[chat_id]
            return

        qidx = state["current"]
        question = state["questions"][state["current"]]
        correct_answer = question['date']
        answers = [correct_answer]

        all_dates = {q['date'] for q in state["questions"] if q['date'] != correct_answer}
        all_dates.add(correct_answer)

        if len(all_dates) < 4:
            while len(all_dates) < 4:
                fake_date = str(int(correct_answer.split(" ")[0]) + random.choice([-5, -4, -3, -2, -1, 1, 2, 3, 4, 5])) + " р."
                if fake_date not in all_dates and fake_date != correct_answer:
                        all_dates.add(fake_date)

            answers = list(all_dates)

        else:
            while len(answers) < 4:
                wrong_answer = random.choice(state["questions"])['date']
                if wrong_answer not in answers:
                    answers.append(wrong_answer)

        answers_kb = types.InlineKeyboardMarkup(row_width=2)
        random.shuffle(answers)
        buttons = [types.InlineKeyboardButton(answer, callback_data=f"answer_{qidx}_{answer}") for answer in answers]
        answers_kb.add(*buttons)

        bot.send_message(chat_id, "❔ " + question['event'], reply_markup=answers_kb)

    if user_state[chat_id]["by_topic"] == False:

        connection = connect_to_db()
        state = user_state.get(chat_id)

        if state is None or state["current"] >= len(state["questions"]):
            bot.send_message(chat_id, f'🔹 Тест по курсу завершено!\n'
                                    f"✅ Правильних відповідей: {state['correct']}\n"
                                    f"❌ Неправильних відповідей: {state['wrong']}")

            with connection.cursor() as cursor:
                cursor.execute(
                    'INSERT INTO results (is_bytheme, chat_id, topic_id, correct_answers, incorrect_answers) VALUES (%s, %s, %s, %s, %s)',
                    (False, chat_id, state.get("topic_id"), state.get("correct", 0), state.get("wrong", 0))
                )
                connection.commit()

            del user_state[chat_id]
            return

        qidx = state["current"]
        question = state["questions"][qidx]
        correct_answer = question['date']
        topic_id = question['topic_id']
        # answers = [correct_answer]

        # all_dates = {q for q in state["questions"] if q["topic_id"] == state["topic_id"]}
        # all_dates.add(correct_answer)

        with connection.cursor() as cursor:
        # Отримуємо 3 випадкові дати з цієї ж теми, крім правильної відповіді
            cursor.execute(
                "SELECT date FROM dates WHERE topic_id = %s AND date != %s ORDER BY RAND() LIMIT 3",
                (topic_id, correct_answer)
            )
            wrong_answers = [row['date'] for row in cursor.fetchall()]

        if len(wrong_answers) < 3:
            # print(state["questions"])
            while len(wrong_answers) < 3:
                fake_date = str(int(correct_answer.split(" ")[0]) + random.choice([-5, -4, -3, -2, -1, 1, 2, 3, 4, 5])) + " р."
                if fake_date not in wrong_answers and fake_date != correct_answer:
                        wrong_answers.append(fake_date)
        else:
            while len(wrong_answers) < 3:
                wrong_answer = random.choice(state["questions"])['date']
                if wrong_answer not in answers:
                    answers.append(wrong_answer)

        answers = [correct_answer] + wrong_answers
        answers_kb = types.InlineKeyboardMarkup(row_width=2)
        random.shuffle(answers)
        buttons = [types.InlineKeyboardButton(answer, callback_data=f"answer_{qidx}_{answer}") for answer in answers]
        answers_kb.add(*buttons)

        bot.send_message(chat_id, "❔ " + question['event'], reply_markup=answers_kb)

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    if call.data == "bycourse_choice":
        connection = connect_to_db()

        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM dates")
            dates = cursor.fetchall()

            if not dates:
                bot.send_message(call.message.chat.id, "На жаль, питань для цього тесту немає.")
                return

        start_quiz_course(call.message.chat.id)

    if call.data == "bytheme_choice":
        topics = get_topics(1, 5)
        limit = 5
        page = 1

        total_topics = get_total_topics()
        total_pages = math.ceil(len(total_topics) / limit)
        topics_keyboard = types.InlineKeyboardMarkup(row_width=1)

        for topic in topics:
            topic_btn = types.InlineKeyboardButton(text=topic['name'], callback_data=f"topic_{topic['id']}")
            topics_keyboard.add(topic_btn)
        
        nav_btns = []
        if page > 1:
            nav_btns.append(types.InlineKeyboardButton(text="⬅️", callback_data=f"page_{page - 1}"))
        if page < total_pages:
            nav_btns.append(types.InlineKeyboardButton(text="➡️", callback_data=f"page_{page + 1}"))

        if nav_btns:
            topics_keyboard.add(*nav_btns)

        bot.send_message(call.message.chat.id, "Обери тему:", reply_markup=topics_keyboard)

    elif call.data.startswith("page_"):
        page = int(call.data.split("_")[1])
        limit = 5

        topics = get_topics(page, limit)

        total_topics = get_total_topics()
        total_pages = math.ceil(len(total_topics) / limit)

        topics_keyboard = types.InlineKeyboardMarkup(row_width=1)

        for topic in topics:
            topic_btn = types.InlineKeyboardButton(text=topic['name'], callback_data=f"topic_{topic['id']}")
            topics_keyboard.add(topic_btn)

        nav_btns = []
        if page > 1:
            nav_btns.append(types.InlineKeyboardButton(text="⬅️", callback_data=f"page_{page - 1}"))
        if page < total_pages:
            nav_btns.append(types.InlineKeyboardButton(text="➡️", callback_data=f"page_{page + 1}"))
        
        if nav_btns:
            topics_keyboard.add(*nav_btns)
        
        bot.edit_message_text(chat_id = call.message.chat.id,
                                message_id = call.message.message_id,
                                text="Обери тему:",
                                reply_markup=topics_keyboard)

    elif call.data.startswith("topic_"):
        topic_id = int(call.data.split("_")[1])
        connection = connect_to_db()

        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM dates WHERE topic_id = %s", (topic_id,))
            dates = cursor.fetchall()

            cursor.execute("SELECT name FROM topics WHERE id = %s", (topic_id,))
            topic_name = cursor.fetchone()["name"]
        
        if not dates:
            bot.send_message(call.message.chat.id, "На жаль, для цієї теми немає запитань.")
            return

        user_state[call.message.chat.id] = {
            "topic_id": topic_id,
            "topic_name": topic_name,
            "questions": dates,
            "current": 0,
            "correct": 0,
            "wrong": 0
        }

        start_quiz_topic(topic_id,
                         call.message.chat.id,
                         topic_name)

    elif call.data.startswith("answer_"):
        chat_id = call.message.chat.id
        state = user_state.get(chat_id)

        if state is None:
            bot.send_message(chat_id, "Помилка: Тест не знайдено.")
            return

        _, qidx, answer = call.data.split("_")
        qidx = int(qidx)
        correct_answer = state["questions"][qidx]['date']

        if answer == correct_answer:
            bot.send_message(chat_id, f"✅ {call.from_user.first_name}, вірно! Правильна відповідь: {correct_answer}")
            state["correct"] += 1
        else:
            bot.send_message(chat_id, f"❌ {call.from_user.first_name}, невірно! Правильна відповідь: {correct_answer}")
            state["wrong"] += 1

        state["current"] += 1
        send_question(chat_id, topic_name=state["topic_name"])

bot.polling(none_stop=True)
