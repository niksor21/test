import telebot
import logging
from gpt import create_promt, ask_gpt, count_tokens_in_dialogue
from config import BOT_TOKEN, MAX_USERS, MAX_SESSIONS, MAX_USER_TOKENS

bot = telebot.TeleBot(BOT_TOKEN)

current_options = {}
exist_options = {
    'genres_list': ["Хоррор", "Юмор", "Фэнтези"],
    'characters_list': ["Инкассатор-детектив", "Илон Маск", "Девочка-викинг", "Белка Сэнди из Спанч-Боба"],
    'settings_list': ["Космическая Станция 'Аврора'", "Магический лес Гриндейл", "Ярмарка в центре деревни"]
}

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

# Подключаем логирование
file_handler = logging.FileHandler("log_file.txt", mode="w", encoding="utf-8")
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
datefmt = "%Y-%m-%d %H:%M:%S"
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)


# Отправляем пользователю файл с логами по команде /debug
@bot.message_handler(commands=['debug'])
def handle_debug(message):
    logging.info("Отправка файла логов пользователю")
    try:
        with open("log_file.txt", "rb") as file:
            bot.send_document(message.from_user.id, file)
    except Exception as e:
        bot.send_message(message.from_user.id, f"Произошла ошибка при отправке лога: {str(e)}")


def create_keyboard(options):
    buttons = []
    for opt in options:
        buttons.append(telebot.types.KeyboardButton(text=opt))

    keyboard = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    keyboard.add(*buttons)
    return keyboard


def can_text(user_id):
    bot.send_message(user_id, text='Привет! К сожалению, существует ограничение на количество пользователей '
                                   'и сессий для каждого из пользователей, :( Ты не сможешь составить сценарий')


@bot.message_handler(commands=['start'])
def start(message):
    global current_options
    user_id = message.from_user.id

    if len(current_options) >= MAX_USERS:
        can_text(user_id)
        return

    bot.send_message(user_id,
                     text=f"Привет! \n\nЯ бот-сценарист, который учился в Нью-Йоркской Академии Киноискусства.\n\n"
                          f"Ладно, шучу :) Но я могу придумать сценарий для твоей истории.\n\n"
                          f"Выбери жанр, персонажей и локацию, а я тут насочиняю ✍️",
                     reply_markup=create_keyboard(['/write_scenario']))

    if user_id not in current_options:
        current_options[user_id] = {
            'session': 1,
            'genre': '',
            'character': '',
            'setting': '',
            'additionally': '',
            'tokens': 0,
            'debug': False
        }


@bot.message_handler(commands=['write_scenario'])
def write_scenario(message):
    global exist_options

    user_id = message.from_user.id

    if len(current_options) >= MAX_USERS:
        can_text(user_id)
        return

    keyboard = telebot.types.InlineKeyboardMarkup()
    keyboard.add(telebot.types.InlineKeyboardButton("debug", callback_data="debug"))

    bot.send_message(user_id, text='Выбери жанр, в котором будем писать историю.',
                     reply_markup=create_keyboard(exist_options['genres_list']))
    bot.send_message(user_id, text='Если хочешь, чтобы тебе приходили сообщения с информацией о том, '
                                   'что происходит в боте, то нажми на debug (но лучше не надо).\n\n'
                                   'А еще у нас есть волшебная команда /debug, которая пришлет файл с логами.',
                     reply_markup=keyboard)

    bot.register_next_step_handler(message, genre_choose)


@bot.callback_query_handler(func=lambda call: True)
def answer(call):
    global current_options
    if call.data == 'debug':
        current_options[call.from_user.id]['debug'] = True
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id,
                              text='Включен режим дебага')


def genre_choose(message):
    global current_options
    global exist_options

    genre = message.text
    user_id = message.from_user.id

    if genre not in exist_options['genres_list']:
        bot.send_message(user_id, text='Выбран несуществующий жанр')
        write_scenario(message)
        return

    if current_options[user_id]['debug']:
        bot.send_message(user_id, text=f'Выбран жанр "{genre}"')

    current_options[user_id]['genre'] = genre
    bot.send_message(user_id, text='Давай теперь выберем персонажа',
                     reply_markup=create_keyboard(exist_options['characters_list']))
    bot.register_next_step_handler(message, character_choose)


def character_choose(message):
    global current_options
    global exist_options

    character = message.text
    user_id = message.from_user.id

    if character not in exist_options['characters_list']:
        bot.send_message(user_id, text='Выбран несуществующий персонаж')
        write_scenario(message)
        return

    if current_options[user_id]['debug']:
        bot.send_message(user_id, text=f'Выбран герой "{character}"')

    current_options[user_id]['character'] = character
    bot.send_message(user_id, text='А теперь давай выберем локацию.',
                     reply_markup=create_keyboard(exist_options['settings_list']))
    bot.register_next_step_handler(message, setting_choose)


def setting_choose(message):
    global current_options
    global exist_options

    setting = message.text
    user_id = message.from_user.id

    if setting not in exist_options['settings_list']:
        bot.send_message(user_id, text='Выбрана несуществующая локация')
        write_scenario(message)
        return

    if current_options[user_id]['debug']:
        bot.send_message(user_id, text=f'Выбрана локация "{setting}"')

    current_options[user_id]['setting'] = setting
    bot.send_message(user_id, text='Все выбрано. Нужно ли внести дополнительную информацию? Тогда напиши ее!\n\n'
                                   'Если же дополнять не хочешь, то просто вызови команду /begin',
                     reply_markup=create_keyboard(['/begin']))
    bot.register_next_step_handler(message, begin)


@bot.message_handler(commands=['begin'])
def begin(message):
    global current_options

    user_id = message.from_user.id
    text = message.text

    if len(current_options) >= MAX_USERS:
        can_text(user_id)
        return

    if user_id not in current_options:
        bot.send_message(user_id, text='Ты пока не регистрировался и не выбирал, '
                                       'из каких частей будет состоять твой сценарий. Тыкни на /start',
                         reply_markup=create_keyboard(['/start']))
        return

    if current_options[user_id]['session'] > MAX_SESSIONS:
        can_text(user_id)
        return

    if text != '/begin':
        current_options[user_id]['additionally'] = text
        bot.send_message(user_id, text='Ну теперь точно жми /begin', reply_markup=create_keyboard(['/begin']))
        return

    promt = create_promt(current_options, user_id)

    bot.send_message(user_id, text='Сочиняю...✍️')

    if current_options[user_id]['debug']:
        bot.send_message(user_id, text=f'Происходит генерация ответа')

    collection = [
        {'role': 'system', 'text': promt}
    ]

    result, status = ask_gpt(collection)

    if not status:
        bot.send_message(user_id, text='Произошла ошибка, попробуйте снова чуть позже',
                         reply_markup=create_keyboard(['/start']))
        if current_options[user_id]['debug']:
            bot.send_message(user_id, text=f'Произошла ошибка {result}')
        return

    collection.append({'role': 'assistant', 'text': result})
    tokens = count_tokens_in_dialogue(collection)
    current_options[user_id]['tokens'] += tokens

    if current_options[user_id]['tokens'] >= MAX_USER_TOKENS:
        bot.send_message(user_id, text=result)
        bot.send_message(user_id, text='Количество токенов в рамках текущей сессии закончилось. '
                                       'Началась следующая сессия. Хотел бы попробовать снова?',
                         reply_markup=create_keyboard(['/write_scenario']))
        current_options[user_id]['session'] += 1
        return

    bot.send_message(user_id, text=result)
    bot.send_message(user_id, text='Хотел бы попробовать снова? Нажми /write_scenario',
                     reply_markup=create_keyboard(['/write_scenario']))


bot.polling()
