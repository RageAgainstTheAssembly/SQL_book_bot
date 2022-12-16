import logging
import constants as keys
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, CallbackContext
import psycopg2 as sql
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext

global query_data
global page_num
global query_ids
global query_prices
query_ids = None
query_prices = None
page_num = 0
page_size = 50

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)


def get_ids(data):
    ids = [None] * len(data)
    i = 0
    for e in data:
        ids[i] = e[1]
        i += 1
    return ids


def get_prices(data):
    prices = [None] * len(data)
    i = 0
    for e in data:
        prices[i] = e[2]
        i += 1
    return prices


def cart_to_string(data):
    total = 0
    output = "Cart contents: \n\n\n"
    for i in data:
        output += str(i[0]) + f" ({int(i[1])} RUB)" + '\n\n'
        total += int(i[1])
    return output + f"Total price: {total}"


def query_parser(data, n, page_size):
    output = ""
    i = 1
    for e in data:
        output += str(i + page_size * n) + ') '
        output += str(e[0]) + f" ({int(e[2])} RUB)"
        output += '\n\n'
        i += 1
    return output + 'Page #' + str(n + 1)


def info_parser(data):
    covertype_id = data[1]
    cur.execute('SELECT name FROM bsp.covertype WHERE id=' + str(covertype_id))
    cover = str(cur.fetchone()[0])

    publisher_id = data[2]
    cur.execute('SELECT name FROM bsp.publisher WHERE id=' + str(publisher_id))
    publisher = str(cur.fetchone()[0])

    publicationdate = data[3]
    title = data[4]
    author = data[5]
    description = data[6]
    language = data[7]
    pagecount = data[8]
    isbn = data[9]
    meanrating = data[10]
    output = ''
    output += 'Title: \n' + str(title) + '\n\n'
    output += 'Author: \n' + str(author) + '\n\n'
    output += 'Description: \n' + str(description) + '\n\n'
    output += 'Publisher: \n' + str(publisher) + '\n\n'
    output += 'Cover type: \n' + str(cover) + '\n\n'
    output += 'Publication date: \n' + str(publicationdate) + '\n\n'
    output += 'Language: \n' + str(language) + '\n\n'
    output += 'Number of pages: \n' + str(pagecount) + '\n\n'
    output += 'Rating: \n' + str(meanrating) + '\n\n'
    output += 'ISBN#: \n' + str(isbn) + '\n\n'

    return output


def menu_command(update: Update, context: CallbackContext) -> None:
    """Sends a message with inline button attached."""
    keyboard = [
        [InlineKeyboardButton("See all available books", callback_data='all')],
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    update.message.reply_text('Please choose:', reply_markup=reply_markup)


def button(update: Update, context: CallbackContext) -> None:
    global query_data
    global page_num
    global page_size
    global query_ids
    global query_prices
    page_num = 0
    """Parses the CallbackQuery and updates the message text."""
    query = update.callback_query
    page_size = 50
    query_ids = None

    # CallbackQueries need to be answered, even if no notification to the user is needed
    # Some clients may have trouble otherwise. See https://core.telegram.org/bots/api#callbackquery
    query.answer()

    if query.data == "all":
        cur.execute('SELECT title, bsp.edition.id, price FROM bsp.edition JOIN bsp.bookinstance on bsp.edition.id=bsp.bookinstance.id WHERE isavailable=true ORDER BY meanrating DESC NULLS LAST')
        query_data = cur.fetchall()
        query_ids = get_ids(query_data)
        query_prices = get_prices(query_data)
        print(query_prices)
        text = query_parser(query_data[0:page_size], page_num, page_size)
        try:
            query.edit_message_text(text=text)
        except:
            print('WARNING: Telegram bad edit request')


def next_command(update: Update, context: CallbackContext) -> None:
    global page_num
    global query_data
    global page_size
    global query_ids
    page_num += 1
    text = query_parser(query_data[page_num * page_size : (page_num + 1) * page_size], page_num, page_size)
    update.message.reply_text(text=text)


def register_user(user_id, username):
    try:
        cur.execute(f"INSERT INTO bsp.user VALUES ({int(user_id)}, '{str(username)}', 'password', true)")
        conn.commit()
        print(f"Registering user {int(user_id)}")
    except:
        print(f"User {int(user_id)} already registered")
    cur.execute("SELECT MAX(id) FROM bsp.purchase")
    purchase_id = int(cur.fetchone()[0]) + 1
    cur.execute(f"INSERT INTO bsp.purchase(id, buyer_id, iscart, deliverytype, deliveryaddress) VALUES ({purchase_id}, {int(user_id)}, true, 'delivery', 'Myasnitskaya, 20')")
    conn.commit()


def add_to_cart(update: Update, context: CallbackContext) -> None:
    global query_ids
    global cart
    global query_data
    query_ids = get_ids(query_data)
    user_message = str(update.message.text).split()
    command = user_message[0].lower()
    option = user_message[1].lower()

    if command == 'add':
        n = int(user_message[1]) - 1
        user_data = update.message.from_user
        user_id = user_data['id']
        username = user_data['username']
        book_id = query_ids[n]

        # let's see if user already has a purchase
        cur.execute(f"SELECT count(1) > 0 FROM bsp.purchase WHERE buyer_id ={int(user_id)}")
        has_purchase = bool(cur.fetchone()[0])


        if not has_purchase:
            # add user to DB if not there already
            # also create a purchase for them
            register_user(user_id, username)

        try:
            # get purchase id for current user
            cur.execute(f"SELECT id FROM bsp.purchase WHERE buyer_id ={int(user_id)}")
            purchase_id = int(cur.fetchone()[0])
            #get book id
            book_id = query_ids[n]
            # let's see if book already in cart
            cur.execute(f"SELECT count(1) > 0 FROM bsp.purchase_bookinstance_includes WHERE bookinstance_id = {int(book_id)}")
            already_in_cart = bool(cur.fetchone()[0])
            if not already_in_cart:
                #push book id to purchase contains table
                cur.execute(f"INSERT INTO bsp.purchase_bookinstance_includes VALUES({int(purchase_id)}, '{int(book_id)}')")
                update.message.reply_text(text='Book "' + str(query_data[n][0]) + '" added to cart')
            if already_in_cart:
                update.message.reply_text(text='That book is already in your cart')
        except:
            update.message.reply_text(text='Invalid book number')

    if command == 'info':
        n = int(user_message[1]) - 1
        id = query_ids[n]
        cur.execute('SELECT * FROM bsp.edition WHERE id=' + str(id))
        info = cur.fetchone()
        update.message.reply_text(text=info_parser(info))


def clear_command(update: Update, context: CallbackContext) -> None:
    user_data = update.message.from_user
    user_id = user_data['id']
    # get purchase id for current user
    cur.execute(f"SELECT id FROM bsp.purchase WHERE buyer_id ={int(user_id)}")
    purchase_id = int(cur.fetchone()[0])
    cur.execute(f"DELETE FROM bsp.purchase_bookinstance_includes WHERE purchase_id={int(purchase_id)};")
    update.message.reply_text(text='Cart has been cleared')


def cart_command(update: Update, context: CallbackContext) -> None:
    global query_data
    user_data = update.message.from_user
    user_id = user_data['id']
    # get purchase id for current user
    cur.execute(f"SELECT id FROM bsp.purchase WHERE buyer_id ={int(user_id)}")
    try:
        purchase_id = int(cur.fetchone()[0])
    except:
        update.message.reply_text(text='Cart is empty')
    #get titles in cart
    cur.execute(f"SELECT title, price FROM (bsp.purchase_bookinstance_includes JOIN bsp.edition ON bookinstance_id=id) JOIN bsp.bookinstance on bookinstance_id = bsp.bookinstance.id WHERE purchase_id={int(purchase_id)}")
    books_in_cart = cur.fetchall()
    if len(books_in_cart) == 0:
        update.message.reply_text(text='Cart is empty')
    else:
        update.message.reply_text(text=cart_to_string(books_in_cart))


def buy_command(update: Update, context: CallbackContext) -> None:
    clear_command(update, context)
    update.message.reply_text(text='Order complete, cart cleared')


def main() -> None:
    """Run the bot."""
    # Create the Updater and pass it your bot's token.
    updater = Updater(keys.API_KEY)

    #connect to database


    updater.dispatcher.add_handler(CommandHandler('menu', menu_command))
    updater.dispatcher.add_handler(CallbackQueryHandler(button))
    updater.dispatcher.add_handler(CommandHandler('next', next_command))
    updater.dispatcher.add_handler(CommandHandler('cart', cart_command))
    updater.dispatcher.add_handler(CommandHandler('clear', clear_command))
    updater.dispatcher.add_handler(CommandHandler('buy', buy_command))
    updater.dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, add_to_cart))

    # Start the Bot
    updater.start_polling()

    # Run the bot until the user presses Ctrl-C or the process receives SIGINT,
    # SIGTERM or SIGABRT
    updater.idle()


conn = sql.connect(
        host="84.201.135.211",
        database="adv1",
        user="u_adventure",
        password="HSEP@ssword2022")
conn.autocommit = True
# create a cursor
cur = conn.cursor()

# execute a statement
print('PostgreSQL database version:')
cur.execute('SELECT version()')

# display the PostgreSQL database server version
db_version = cur.fetchone()
print(db_version)

main()
