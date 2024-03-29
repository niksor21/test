import json
import logging

import telebot
from telebot.types import Message

import db
from config import ADMINS, LOGS_PATH, MAX_TOKENS_PER_SESSION, MAX_SESSIONS, MAX_USERS, MAX_MODEL_TOKENS, BOT_TOKEN
from gpt import ask_gpt_helper, count_tokens_in_dialogue, get_system_content
from utils import create_keyboard

# Инициируем логгер по пути константы с уровнем логгирования debug
logging.basicConfig(
    filename=LOGS_PATH,
    level=logging.DEBUG,
    format="%(asctime)s %(message)s",
    filemode="w",
)

# Создаем клиент нашего бота
bot = telebot.TeleBot(BOT_TOKEN)

# Создаем базу и табличку в ней
db.create_db()
db.create_table()

# Определяем списки жанров, персонажей и сеттингов
genre_list = ["Хоррор", "Юмор", "Фэнтези"]
character_list = ["Инкассатор-детектив", "Илон Маск", "Девочка-викинг", "Белка Сэнди из Спанч-Боба"]
setting_list = ["Космическая Станция 'Аврора'", "Магический лес Гриндейл", "Ярмарка в центре деревни"]


@bot.message_handler(commands=["start"])
def start(message):
    user_name = message.from_user.first_name  # Получаем имя пользователя
    user_id = message.from_user.id  # Получаем id пользователя

    if not db.is_user_in_db(user_id):  # Если пользователя в базе нет
        if len(db.get_all_users_data()) < MAX_USERS:  # Если число зарегистрированных пользователей меньше допустимого
            db.add_new_user(user_id)  # Регистрируем нового пользователя
        else:
            # Если уперлись в лимит пользователей, отправляем сообщение об этом
            bot.send_message(
                user_id,
                "К сожалению, лимит пользователей исчерпан. "
                "Вас много, а я одна (с) :("
            )
            return  # Прерываем здесь функцию, чтобы дальнейший код не выполнялся

    # Этот блок срабатывает только для зарегистрированных пользователей
    bot.send_message(
        user_id,
        f"Привет, {user_name}! \n\nЯ бот-сценарист, который учился в Нью-Йоркской Академии Киноискусства.\n\n"
        f"Ладно, шучу :) Но я могу придумать сценарий для твоей истории.\n\n"
        f"Выбери жанр, персонажей и локацию, а я тут насочиняю ✍️",
        reply_markup=create_keyboard(["Выбрать жанр"]),  # Добавляем кнопочку для ответа
    )
    # Насильно уводим пользователя в функцию выбора жанра (независимо от того нажмет ли он кнопку или отправит
    # какое-нибудь другое сообщение)
    bot.register_next_step_handler(message, choose_genre)


# Функция фильтр для хэндлера выбора жанра (создания новой сессии)
def filter_choose_genre(message: Message) -> bool:
    user_id = message.from_user.id
    if db.is_user_in_db(user_id):  # Отработает только для зарегистрированных пользователей
        return message.text in ["Выбрать жанр", "Выбрать другой жанр", "Начать новую сессию"]


@bot.message_handler(func=filter_choose_genre)
def choose_genre(message: Message):
    user_id = message.from_user.id
    sessions = db.get_user_data(user_id)["sessions"]  # Получаем из БД актуальное количество сессий пользователя
    if sessions < MAX_SESSIONS:  # Если число сессий пользователя не достигло предела
        db.update_row(user_id, "sessions", sessions + 1)  # Накручиваем ему +1 сессию
        db.update_row(user_id, "tokens", MAX_TOKENS_PER_SESSION)  # И обновляем его токены
        bot.send_message(
            user_id,
            "Выбери жанр, в котором будем писать историю:",
            reply_markup=create_keyboard(genre_list),  # Создаем клавиатуру из списка жанров
        )
        bot.register_next_step_handler(message, genre_selection)  # Принудительно уводим в функцию выбора персонажа

    else:  # Если число сессий достигло лимита
        bot.send_message(
            user_id,
            "К сожалению, лимит твоих вопросов исчерпан :("
        )


def genre_selection(message: Message):
    user_id = message.from_user.id
    user_choice = message.text  # Получаем выбор жанра пользователя
    if user_choice in genre_list:  # Проверим, что жанр есть в списке
        db.update_row(user_id, "genre", user_choice)  # Обновим значение жанра в БД
        bot.send_message(
            user_id,
            f"Отлично, {message.from_user.first_name}, я напишу историю в жанре '{user_choice}'!\n\n"
            f"Давай теперь выберем персонажа:",
            reply_markup=create_keyboard(character_list),  # Создаем клавиатуру выбора персонажа из списка
        )
        bot.register_next_step_handler(message, character_selection)  # Принудительно уводим в обработчик выбора сеттинга

    else:  # Если был выбран предмет не из нашего списка
        bot.send_message(
            user_id,
            "К сожалению, такой жанр я пока не знаю, просто выбери один из предложенных в меню",
            reply_markup=create_keyboard(genre_list),
        )
        bot.register_next_step_handler(message, genre_selection)  # Снова отправляем его в эту же функцию


def filter_choose_character(message: Message) -> bool:
    user_id = message.from_user.id
    if db.is_user_in_db(user_id):
        return message.text == "Изменить персонажа"


# Выбор уровня персонажа построен аналогично выбору жанра, поэтому тут не расписываю
@bot.message_handler(func=filter_choose_character)
def choose_character(message: Message):
    bot.send_message(
        message.from_user.id,
        "Какого персонажа ты выберешь:",
        reply_markup=create_keyboard(character_list),
    )
    bot.register_next_step_handler(message, character_selection)


def character_selection(message: Message):
    user_id = message.from_user.id
    user_choice = message.text
    if user_choice in character_list:
        db.update_row(user_id, "character", user_choice)
        bot.send_message(
            user_id,
            f"Принято, {message.from_user.first_name}! Нашим персонажем будет '{user_choice}'.\n\n"
            f"А теперь давай выберем локацию.",
            reply_markup=create_keyboard(setting_list),  # Создаем клавиатуру выбора сеттинга из списка
        )
        bot.register_next_step_handler(message, setting_selection)
    else:
        bot.send_message(
            user_id,
            "Пожалуйста, выбери персонажа из предложенных:",
            reply_markup=create_keyboard(character_list),
        )
        bot.register_next_step_handler(message, character_selection)


def filter_choose_setting(message: Message) -> bool:
    user_id = message.from_user.id
    if db.is_user_in_db(user_id):
        return message.text == "Изменить локацию"


@bot.message_handler(func=filter_choose_setting)
def choose_setting(message: Message):
    bot.send_message(
        message.from_user.id,
        "Какая локацию ты выберешь:",
        reply_markup=create_keyboard(setting_list),
    )
    bot.register_next_step_handler(message, setting_selection)


# Выбираем уровень сложности
def setting_selection(message: Message):
    user_id = message.from_user.id
    user_choice = message.text
    if user_choice in setting_list:
        db.update_row(user_id, "setting", user_choice)
        bot.send_message(
            user_id,
            f"Принято, {message.from_user.first_name}! Наша локация: '{user_choice}'.\n\n"
            f"Если хочешь напиши важную деталь, которую я должен учесть в этой истории. Если добавить нечего, отправь точку или смайлик.",
        )
        bot.register_next_step_handler(message, give_answer)
    else:
        bot.send_message(
            user_id,
            "Пожалуйста, выбери локацию из предложенных:",
            reply_markup=create_keyboard(setting_list),
        )
        bot.register_next_step_handler(message, setting_selection)


def filter_solve_task(message: Message) -> bool:
    user_id = message.from_user.id
    if db.is_user_in_db(user_id):
        return message.text == "Придумать что-то ещё"


# Блок решения задач
@bot.message_handler(func=filter_solve_task)
def solve_task(message):
    bot.send_message(message.from_user.id, "Напиши важную деталь, которую я должен учесть в этой истории. Если добавить нечего, отправь точку или смайлик.")  # Просим пользователя ввести вопрос
    bot.register_next_step_handler(message, give_answer)  # И принудительно уводим в функцию предоставления ответа


def give_answer(message: Message):
    user_id = message.from_user.id
    user_tokens = db.get_user_data(user_id)["tokens"]  # Получаем актуальное количество токенов пользователя из БД
    genre = db.get_user_data(user_id)["genre"]  # Получаем выбранный жанр из БД
    character = db.get_user_data(user_id)["character"]  # Получаем выбранного персонажа из БД
    setting = db.get_user_data(user_id)["setting"]  # Получаем выбранный сеттинг из БД

    user_content = message.text  # Формируем user_content из сообщения пользователя
    system_content = get_system_content(genre, character, setting)  # Формируем system_content из предмета и сложности

    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_content}
    ]  # Приводим контент к стандартизированному виду - списку из словарей сообщений
    tokens_messages = count_tokens_in_dialogue(messages)  # Посчитаем вес запроса в токенах

    if tokens_messages + MAX_MODEL_TOKENS <= user_tokens:  # Проверим что вес запроса + максимального ответа меньше, чем
        # оставшееся количество токенов у пользователя, чтобы пользователю хватило и на запрос и на максимальный ответ
        bot.send_message(message.from_user.id, "Сочиняю ✍️...")
        answer = ask_gpt_helper(messages)  # Получаем ответ от GPT
        messages.append({"role": "assistant", "content": answer})  # Добавляем в наш словарик ответ GPT

        user_tokens -= count_tokens_in_dialogue([{"role": "assistant", "content": answer}])  # Получаем новое значение
        # оставшихся токенов пользователя - вычитаем стоимость запроса и ответа
        db.update_row(user_id, "tokens", user_tokens)  # Записываем новое значение в БД

        json_string = json.dumps(messages, ensure_ascii=False)  # Преобразуем список словарей сообщений к виду json
        # строки для хранения в одной ячейке БД
        db.update_row(user_id, "messages", json_string)  # Записываем получившуюся строку со всеми
        # сообщениями в ячейку 'messages'

        if answer is None:
            bot.send_message(
                user_id,
                "Не могу получить ответ от GPT :(",
                reply_markup=create_keyboard(
                    [
                        "Задать новый вопрос",
                        "Выбрать другой предмет",
                        "Изменить сложность ответов",
                    ]
                ),
            )
        elif answer == "":
            bot.send_message(
                user_id,
                "Не могу сформулировать решение :(",
                reply_markup=create_keyboard(
                    [
                        "Задать новый вопрос",
                        "Выбрать другой предмет",
                        "Изменить сложность ответов",
                    ]
                ),
            )
            logging.info(
                f"Отправлено: {message.text}\nПолучена ошибка: нейросеть вернула пустую строку"
            )
        else:
            bot.send_message(
                user_id,
                answer,
                reply_markup=create_keyboard(
                    [
                        "Задать новый вопрос",
                        "Продолжить объяснение",
                        "Выбрать другой предмет",
                        "Изменить сложность ответов",
                    ]
                ),
            )

    else:  # Если у пользователя не хватает токенов на запрос + ответ
        bot.send_message(
            message.from_user.id,
            "Токенов на ответ может не хватить:( Начни новую сессию",
            reply_markup=create_keyboard(["Начать новую сессию"])  # Предлагаем ему начать новую сессию через кнопку
        )
        logging.info(
            f"Отправлено: {message.text}\nПолучено: Предупреждение о нехватке токенов"
        )


def filter_continue_explaining(message: Message) -> bool:
    user_id = message.from_user.id
    if db.is_user_in_db(user_id):
        return message.text == "Продолжить объяснение"


@bot.message_handler(func=filter_continue_explaining)
def continue_explaining(message):
    user_id = message.from_user.id
    json_string_messages = db.get_user_data(user_id)["messages"]  # Достаем из базы все предыдущие сообщения
    # в виде json-строки
    messages = json.loads(json_string_messages)  # Преобразуем json-строку в нужный нам формат списка словарей
    if not messages:  # Если попытались продолжить, но запроса еще не было
        bot.send_message(
            user_id,
            "Для начала напиши условие задачи:",
            reply_markup=create_keyboard(["Задать новый вопрос"]),
        )
        return  # Прерываем выполнение функции

    user_tokens = db.get_user_data(user_id)["tokens"]  # Получаем актуальное количество токенов пользователя
    tokens_messages = count_tokens_in_dialogue(messages)  # Считаем вес запроса в токенах из всех предыдущих сообщений

    if tokens_messages + MAX_MODEL_TOKENS <= user_tokens:  # Проверяем хватает ли токенов на запрос + ответ
        bot.send_message(user_id, "Формулирую продолжение...")
        answer = ask_gpt_helper(messages)  # Получаем продолжение от gpt
        messages.append({"role": "assistant", "content": answer})  # Добавляем очередной ответ в список сообщений

        user_tokens -= count_tokens_in_dialogue([{"role": "assistant", "content": answer}])  # Вычитаем токены
        db.update_row(user_id, "tokens", user_tokens)  # Сохраняем новое значение токенов в БД

        json_string_messages = json.dumps(messages, ensure_ascii=False)  # Преобразуем список сообщений в строку для БД
        db.update_row(user_id, "messages", json_string_messages)  # Сохраняем строку сообщений в БД

        if answer is None:
            bot.send_message(
                user_id,
                "Не могу получить ответ от GPT :(",
                reply_markup=create_keyboard(
                    [
                        "Задать новый вопрос",
                        "Выбрать другой предмет",
                        "Изменить сложность ответов",
                    ]
                ),
            )
        elif answer == "":
            bot.send_message(
                user_id,
                "Задача полностью решена ^-^",
                reply_markup=create_keyboard(
                    [
                        "Задать новый вопрос",
                        "Выбрать другой предмет",
                        "Изменить сложность ответов",
                    ]
                ),
            )
        else:
            bot.send_message(
                user_id,
                answer,
                reply_markup=create_keyboard(
                    [
                        "Задать новый вопрос",
                        "Продолжить объяснение",
                        "Выбрать другой предмет",
                        "Изменить сложность ответов",
                    ]
                ),
            )
    else:  # Если токенов на продолжение не хватило
        bot.send_message(
            message.from_user.id,
            "Токенов на ответ может не хватить:( Пожалуйста, попробуй укоротить вопрос. "
            "или задай новый",
            reply_markup=create_keyboard(["Задать новый вопрос"]),  # Предлагаем задать новый вопрос в рамках сессии
        )
        logging.info(
            f"Отправлено: {message.text}\nПолучено: Предупреждение о нехватке токенов"
        )


@bot.message_handler(commands=["debug"])
def send_logs(message):
    user_id = message.from_user.id
    if user_id in ADMINS:
        with open(LOGS_PATH, "rb") as f:
            bot.send_document(message.from_user.id, f)


bot.polling()
