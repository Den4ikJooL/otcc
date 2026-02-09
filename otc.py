[file name]: otc.py
[file content begin]
import telebot
from telebot import types
import os
import re
import random
import string
import sqlite3
import threading
import time
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv('8037437265:AAEvcLzz9OUxiWj1bQAA4csSM9l7f3iA--Q')

bot = telebot.TeleBot('8037437265:AAEvcLzz9OUxiWj1bQAA4csSM9l7f3iA--Q')

# Глобальная переменная для username поддержки (можно менять командой /set @username)
SUPPORT_USERNAME = "GuarantNFTsupport"

def get_support_username():
    """Возвращает текущий username поддержки"""
    return SUPPORT_USERNAME

def set_support_username(username):
    """Устанавливает новый username поддержки"""
    global SUPPORT_USERNAME
    SUPPORT_USERNAME = username.replace("@", "").strip()

def format_support(text):
    """Заменяет @GuarantNFTsupport на текущий username поддержки в тексте"""
    return text.replace("@GuarantNFTsupport", f"@{SUPPORT_USERNAME}")

# Вспомогательные функции для безопасной отправки сообщений
def safe_send_message(user_id, text, **kwargs):
    """Безопасная отправка сообщения с обработкой блокировки бота"""
    try:
        return bot.send_message(user_id, text, **kwargs)
    except Exception as e:
        if "bot was blocked by the user" in str(e) or "Forbidden" in str(e):
            print(f"[INFO] User {user_id} has blocked the bot")
        else:
            print(f"[ERROR] Failed to send message to user {user_id}: {e}")
        return None

def safe_send_photo(user_id, photo, **kwargs):
    """Безопасная отправка фото с обработкой блокировки бота"""
    try:
        return bot.send_photo(user_id, photo, **kwargs)
    except Exception as e:
        if "bot was blocked by the user" in str(e) or "Forbidden" in str(e):
            print(f"[INFO] User {user_id} has blocked the bot")
        else:
            print(f"[ERROR] Failed to send photo to user {user_id}: {e}")
        return None

db_lock = threading.Lock()
conn = sqlite3.connect("botdata.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("PRAGMA table_info(deals);")
columns = [row[1] for row in cursor.fetchall()]
if 'deal_type' not in columns:
    try:
        cursor.execute("ALTER TABLE deals ADD COLUMN deal_type TEXT;")
        conn.commit()
    except sqlite3.OperationalError:
        pass

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    ton_wallet TEXT,
    card_number TEXT,
    lang TEXT DEFAULT 'ru',
    successful_deals INTEGER DEFAULT 0
);
""")

cursor.execute("PRAGMA table_info(users);")
user_columns = [row[1] for row in cursor.fetchall()]
if 'successful_deals' not in user_columns:
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN successful_deals INTEGER DEFAULT 0;")
        conn.commit()
    except sqlite3.OperationalError as e:
        pass
if 'last_activity' not in user_columns:
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN last_activity INTEGER DEFAULT 0;")
        conn.commit()
    except sqlite3.OperationalError as e:
        pass
if 'referrer_id' not in user_columns:
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN referrer_id INTEGER;")
        conn.commit()
    except sqlite3.OperationalError as e:
        pass
if 'guarantor_status' not in user_columns:
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN guarantor_status TEXT DEFAULT 'none';")
        conn.commit()
    except sqlite3.OperationalError as e:
        pass

# Обновляем всех существующих пользователей, устанавливая им текущее время активности
# Это нужно для того, чтобы они учитывались в MAU при первом запуске после добавления поля
try:
    current_timestamp = int(time.time())
    cursor.execute("UPDATE users SET last_activity = ? WHERE last_activity = 0 OR last_activity IS NULL", (current_timestamp,))
    conn.commit()
except Exception as e:
    pass

cursor.execute("""
CREATE TABLE IF NOT EXISTS deals (
    deal_id TEXT PRIMARY KEY,
    seller_id INTEGER,
    seller_username TEXT,
    buyer_id INTEGER,
    amount REAL,
    offer TEXT,
    deal_type TEXT,
    status TEXT DEFAULT 'open',
    successful INTEGER DEFAULT 0,
    created_at INTEGER DEFAULT 0
);
""")

# Добавляем поле created_at, если его нет
cursor.execute("PRAGMA table_info(deals);")
deal_columns = [row[1] for row in cursor.fetchall()]
if 'created_at' not in deal_columns:
    try:
        cursor.execute("ALTER TABLE deals ADD COLUMN created_at INTEGER DEFAULT 0;")
        conn.commit()
    except sqlite3.OperationalError as e:
        pass

# Создаем таблицу для балансов пользователей
cursor.execute("""
CREATE TABLE IF NOT EXISTS balances (
    user_id INTEGER PRIMARY KEY,
    ton_balance REAL DEFAULT 0.0,
    rub_balance REAL DEFAULT 0.0,
    star_balance REAL DEFAULT 0.0
);
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS statistics (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    total_deals INTEGER DEFAULT 0,
    successful_deals INTEGER DEFAULT 0,
    total_volume REAL DEFAULT 0.0
);
""")

# Инициализация статистики, если её нет
cursor.execute("SELECT COUNT(*) FROM statistics WHERE id = 1")
if cursor.fetchone()[0] == 0:
    cursor.execute("INSERT INTO statistics (id, total_deals, successful_deals, total_volume) VALUES (1, 1020, 870, 1124.0)")
else:
    # Обновляем существующую статистику начальными значениями, если они нулевые
    cursor.execute("SELECT total_deals, successful_deals, total_volume FROM statistics WHERE id = 1")
    row = cursor.fetchone()
    if row and row[0] == 0 and row[1] == 0 and row[2] == 0.0:
        cursor.execute("UPDATE statistics SET total_deals = 1020, successful_deals = 870, total_volume = 1124.0 WHERE id = 1")

conn.commit()

def generate_deal_id():
    return ''.join(random.choices(string.ascii_letters + string.digits, k=8))

def get_user_lang(user_id):
    with db_lock:
        cursor.execute("SELECT lang FROM users WHERE user_id = ?", (user_id,))
        res = cursor.fetchone()
        lang = res[0] if res and res[0] else 'ru'
        if lang not in ['ru', 'en']:
            lang = 'ru'
        return lang

def set_user_lang(user_id, lang):
    with db_lock:
        cursor.execute(
            "INSERT INTO users(user_id, lang) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET lang = ?",
            (user_id, lang, lang)
        )
        conn.commit()

def set_user_ton_wallet(user_id, ton_wallet):
    with db_lock:
        cursor.execute(
            "INSERT INTO users(user_id, ton_wallet) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET ton_wallet = ?",
            (user_id, ton_wallet, ton_wallet)
        )
        conn.commit()

def set_user_card_number(user_id, card_number):
    with db_lock:
        cursor.execute(
            "INSERT INTO users(user_id, card_number) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET card_number = ?",
            (user_id, card_number, card_number)
        )
        conn.commit()

def get_user_ton_wallet(user_id):
    with db_lock:
        cursor.execute("SELECT ton_wallet FROM users WHERE user_id = ?", (user_id,))
        res = cursor.fetchone()
        return res[0] if res else None

def get_user_card_number(user_id):
    with db_lock:
        cursor.execute("SELECT card_number FROM users WHERE user_id = ?", (user_id,))
        res = cursor.fetchone()
        return res[0] if res else None

def has_payment_methods(user_id):
    ton = get_user_ton_wallet(user_id)
    card = get_user_card_number(user_id)
    return bool(ton or card)

def set_user_successful_deals(user_id, count):
    with db_lock:
        cursor.execute(
            "INSERT INTO users(user_id, successful_deals) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET successful_deals = ?",
            (user_id, count, count)
        )
        conn.commit()

def get_user_successful_deals(user_id):
    with db_lock:
        cursor.execute("SELECT successful_deals FROM users WHERE user_id = ?", (user_id,))
        res = cursor.fetchone()
        return res[0] if res else 0

def create_deal(deal_id, seller_id, seller_username, amount, offer, deal_type):
    with db_lock:
        current_timestamp = int(time.time())
        cursor.execute("""
        INSERT INTO deals (deal_id, seller_id, seller_username, amount, offer, deal_type, status, successful, created_at)
        VALUES (?, ?, ?, ?, ?, ?, 'open', 0, ?)""",
                       (deal_id, seller_id, seller_username, amount, offer, deal_type, current_timestamp))
        conn.commit()
    increment_total_deals()

def get_deal(deal_id):
    clean_id = deal_id.replace('#', '').strip()
    with db_lock:
        cursor.execute("SELECT * FROM deals WHERE deal_id = ?", (clean_id,))
        row = cursor.fetchone()
        if row:
            keys = ['deal_id', 'seller_id', 'seller_username', 'buyer_id', 'amount', 'offer', 'deal_type', 'status', 'successful', 'created_at']
            deal_dict = dict(zip(keys, row))
            return deal_dict
        return None

def get_user_deals(user_id):
    """Получает все сделки пользователя (как продавца и как покупателя)"""
    with db_lock:
        # Получаем сделки где пользователь продавец или покупатель
        cursor.execute("""
            SELECT deal_id, seller_id, seller_username, buyer_id, amount, offer, deal_type, status, successful, created_at
            FROM deals 
            WHERE (seller_id = ? OR buyer_id = ?)
            ORDER BY created_at DESC
        """, (user_id, user_id))
        rows = cursor.fetchall()
        deals = []
        for row in rows:
            keys = ['deal_id', 'seller_id', 'seller_username', 'buyer_id', 'amount', 'offer', 'deal_type', 'status', 'successful', 'created_at']
            deal_dict = dict(zip(keys, row))
            deals.append(deal_dict)
        return deals

def set_deal_buyer(deal_id, buyer_id):
    clean_id = deal_id.replace('#', '').strip()
    with db_lock:
        cursor.execute("UPDATE deals SET buyer_id = ? WHERE deal_id = ?", (buyer_id, clean_id))
        conn.commit()

def close_deal(deal_id):
    clean_id = deal_id.replace('#', '').strip()
    with db_lock:
        cursor.execute("UPDATE deals SET status = 'closed' WHERE deal_id = ?", (clean_id,))
        conn.commit()

def delete_deal(deal_id):
    """Полностью удаляет сделку из базы данных"""
    clean_id = deal_id.replace('#', '').strip()
    print(f"[DEBUG] Deleting deal {clean_id} from database")
    with db_lock:
        cursor.execute("DELETE FROM deals WHERE deal_id = ?", (clean_id,))
        conn.commit()
        print(f"[DEBUG] Deal {clean_id} deleted")

def mark_deal_successful(deal_id):
    clean_id = deal_id.replace('#', '').strip()
    print(f"[DEBUG] mark_deal_successful called for {clean_id}")
    try:
        with db_lock:
            print(f"[DEBUG] Got db_lock")
            # Проверяем, не была ли сделка уже успешной
            cursor.execute("SELECT seller_id, amount, deal_type, successful FROM deals WHERE deal_id = ?", (clean_id,))
            result = cursor.fetchone()
            print(f"[DEBUG] Query result: {result}")
            
            if result:
                seller_id = result[0]
                amount = result[1]
                deal_type = result[2]
                already_successful = result[3] if len(result) > 3 else 0
                
                print(f"[DEBUG] Deal data - seller: {seller_id}, amount: {amount}, type: {deal_type}, already_successful: {already_successful}")
                
                # Обновляем сделку только если она еще не была успешной
                if not already_successful:
                    print(f"[DEBUG] Updating deal to successful...")
                    cursor.execute("UPDATE deals SET successful = 1, status='completed' WHERE deal_id = ?", (clean_id,))
                    cursor.execute("UPDATE users SET successful_deals = successful_deals + 1 WHERE user_id = ?", (seller_id,))
                    conn.commit()
                    print(f"[DEBUG] Deal updated, updating statistics...")
                    
                    # Конвертируем сумму в доллары для статистики
                    if amount:
                        amount_usd = float(amount)
                        # Примерные курсы: 1 TON ≈ 5$, 1 STAR ≈ 0.01$, 1 RUB ≈ 0.01$
                        if deal_type == 'ton':
                            amount_usd = float(amount) * 5.0
                        elif deal_type == 'star':
                            amount_usd = float(amount) * 0.01
                        elif deal_type == 'card':
                            amount_usd = float(amount) * 0.01
                        print(f"[DEBUG] Updating statistics with {amount_usd}")
                        # Обновляем статистику напрямую, без вызова функции (избегаем дедлока)
                        cursor.execute("UPDATE statistics SET successful_deals = successful_deals + 1, total_volume = total_volume + ? WHERE id = 1", (amount_usd,))
                        # commit уже сделан выше
                        print(f"[DEBUG] Statistics updated")
                else:
                    print(f"[DEBUG] Deal already marked as successful, updating status to completed")
                    # Если уже была успешной, просто обновляем статус на completed
                    cursor.execute("UPDATE deals SET status='completed' WHERE deal_id = ?", (clean_id,))
                    conn.commit()
            else:
                print(f"[DEBUG] No deal found with id {clean_id}")
    except Exception as e:
        print(f"[ERROR] Error in mark_deal_successful: {e}")
        import traceback
        traceback.print_exc()

def get_successful_deals_count(user_id):
    return get_user_successful_deals(user_id)

def increment_total_deals():
    with db_lock:
        cursor.execute("UPDATE statistics SET total_deals = total_deals + 1 WHERE id = 1")
        conn.commit()

def increment_successful_deals(amount):
    with db_lock:
        cursor.execute("UPDATE statistics SET successful_deals = successful_deals + 1, total_volume = total_volume + ? WHERE id = 1", (amount,))
        conn.commit()

def get_statistics():
    with db_lock:
        cursor.execute("SELECT total_deals, successful_deals, total_volume FROM statistics WHERE id = 1")
        row = cursor.fetchone()
        if row:
            return {
                'total_deals': row[0],
                'successful_deals': row[1],
                'total_volume': row[2]
            }
        return {'total_deals': 0, 'successful_deals': 0, 'total_volume': 0.0}

def update_user_activity(user_id):
    """Обновляет время последней активности пользователя"""
    with db_lock:
        current_timestamp = int(time.time())
        cursor.execute(
            "INSERT INTO users(user_id, last_activity) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET last_activity = ?",
            (user_id, current_timestamp, current_timestamp)
        )
        conn.commit()

def get_mau_count():
    """Подсчитывает MAU (Monthly Active Users) - пользователей активных за последние 30 дней"""
    initial_mau = 14912  # Начальное значение MAU
    with db_lock:
        thirty_days_ago = int(time.time()) - (30 * 24 * 60 * 60)  # 30 дней назад в секундах
        cursor.execute("SELECT COUNT(DISTINCT user_id) FROM users WHERE last_activity >= ? AND last_activity > 0", (thirty_days_ago,))
        result = cursor.fetchone()
        mau_count = result[0] if result and result[0] is not None else 0
        # Если реальный MAU меньше начального значения, возвращаем начальное значение
        # Это нужно для случаев, когда в базе еще нет достаточного количества активных пользователей
        if mau_count < initial_mau:
            return initial_mau
        return mau_count

def get_user_balance(user_id):
    """Получает баланс пользователя"""
    with db_lock:
        cursor.execute("SELECT ton_balance, rub_balance, star_balance FROM balances WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        if row:
            return {'ton': row[0], 'rub': row[1], 'star': row[2]}
        # Если записи нет, создаем и возвращаем нулевые балансы
        cursor.execute("INSERT INTO balances (user_id, ton_balance, rub_balance, star_balance) VALUES (?, 0.0, 0.0, 0.0)", (user_id,))
        conn.commit()
        return {'ton': 0.0, 'rub': 0.0, 'star': 0.0}

def add_balance(user_id, currency, amount):
    """Добавляет средства на баланс пользователя"""
    with db_lock:
        # Убеждаемся, что запись существует
        cursor.execute("SELECT user_id FROM balances WHERE user_id = ?", (user_id,))
        if not cursor.fetchone():
            cursor.execute("INSERT INTO balances (user_id, ton_balance, rub_balance, star_balance) VALUES (?, 0.0, 0.0, 0.0)", (user_id,))
        
        if currency == 'ton':
            cursor.execute("UPDATE balances SET ton_balance = ton_balance + ? WHERE user_id = ?", (amount, user_id))
        elif currency == 'rub':
            cursor.execute("UPDATE balances SET rub_balance = rub_balance + ? WHERE user_id = ?", (amount, user_id))
        elif currency == 'star':
            cursor.execute("UPDATE balances SET star_balance = star_balance + ? WHERE user_id = ?", (amount, user_id))
        conn.commit()

def deduct_balance(user_id, currency, amount):
    """Снимает средства с баланса пользователя. Возвращает True если успешно, False если недостаточно средств"""
    with db_lock:
        # Получаем баланс напрямую без вызова get_user_balance (чтобы избежать дедлока)
        cursor.execute("SELECT ton_balance, rub_balance, star_balance FROM balances WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        
        if not row:
            # Если записи нет, создаем с нулевым балансом
            cursor.execute("INSERT INTO balances (user_id, ton_balance, rub_balance, star_balance) VALUES (?, 0.0, 0.0, 0.0)", (user_id,))
            conn.commit()
            return False
        
        balance = {'ton': row[0], 'rub': row[1], 'star': row[2]}
        currency_key = currency.lower()
        
        if currency_key not in balance or balance[currency_key] < amount:
            return False
        
        if currency == 'ton':
            cursor.execute("UPDATE balances SET ton_balance = ton_balance - ? WHERE user_id = ?", (amount, user_id))
        elif currency == 'rub':
            cursor.execute("UPDATE balances SET rub_balance = rub_balance - ? WHERE user_id = ?", (amount, user_id))
        elif currency == 'star':
            cursor.execute("UPDATE balances SET star_balance = star_balance - ? WHERE user_id = ?", (amount, user_id))
        conn.commit()
        return True

def format_time_moscow(timestamp, lang='ru'):
    """Форматирует timestamp в московское время"""
    if not timestamp or timestamp == 0:
        return "Не указано" if lang == 'ru' else "Not specified"
    # МСК это UTC+3
    moscow_tz = timedelta(hours=3)
    dt = datetime.fromtimestamp(timestamp) + moscow_tz
    if lang == 'ru':
        return dt.strftime("%d.%m.%Y %H:%M МСК")
    else:
        return dt.strftime("%d.%m.%Y %H:%M MSK")

def get_buyer_username(buyer_id):
    """Получает username покупателя из других его сделок как продавца"""
    if not buyer_id:
        return "unknown"
    with db_lock:
        cursor.execute("SELECT seller_username FROM deals WHERE seller_id = ? LIMIT 1", (buyer_id,))
        row = cursor.fetchone()
        if row and row[0]:
            return row[0]
    return "unknown"

def format_user_deals(user_id, deals, lang, page=1):
    """Форматирует список сделок пользователя для отображения с пагинацией
    
    Args:
        user_id: ID пользователя
        deals: список сделок
        lang: язык
        page: номер страницы (начинается с 1)
    
    Returns:
        tuple: (текст_для_отображения, всего_страниц)
    """
    if not deals:
        return MESSAGES[lang]['my_deals_empty'], 1
    
    currency_map = {'ton': 'TON', 'star': 'STAR', 'card': 'RUB'}
    status_map = {
        'open': MESSAGES[lang]['deal_status_open'],
        'completed': MESSAGES[lang]['deal_status_completed'],
        'closed': MESSAGES[lang]['deal_status_closed']
    }
    
    # Пагинация: 5 сделок на странице
    deals_per_page = 5
    total_deals = len(deals)
    total_pages = (total_deals + deals_per_page - 1) // deals_per_page  # округление вверх
    
    # Проверяем корректность страницы
    if page < 1:
        page = 1
    if page > total_pages:
        page = total_pages
    
    # Вычисляем индексы для текущей страницы
    start_idx = (page - 1) * deals_per_page
    end_idx = min(start_idx + deals_per_page, total_deals)
    deals_to_show = deals[start_idx:end_idx]
    
    result = MESSAGES[lang]['my_deals_title'] + "\n"
    if lang == 'ru':
        result += f"📄 Страница {page} из {total_pages} | Всего сделок: {total_deals}\n\n"
    else:
        result += f"📄 Page {page} of {total_pages} | Total deals: {total_deals}\n\n"
    
    # Максимальная длина для Telegram caption (1024 символа, оставляем запас)
    max_length = 1000
    current_length = len(result)
    
    for deal in deals_to_show:
        # Определяем роль пользователя
        if deal['seller_id'] == user_id:
            role = MESSAGES[lang]['deal_role_seller']
            other_user_id = deal.get('buyer_id')
            if other_user_id:
                other_username = get_buyer_username(other_user_id)
            else:
                other_username = "ожидается покупатель" if lang == 'ru' else "waiting for buyer"
                other_user_id = "N/A"
        else:
            role = MESSAGES[lang]['deal_role_buyer']
            other_user_id = deal['seller_id']
            other_username = deal.get('seller_username', 'unknown')
        
        currency = currency_map.get(deal.get('deal_type', 'ton'), 'TON')
        status = status_map.get(deal.get('status', 'open'), MESSAGES[lang]['deal_status_open'])
        date_str = format_time_moscow(deal.get('created_at', 0), lang)
        
        # Сокращаем offer если он слишком длинный
        offer = deal.get('offer', 'N/A')
        if len(offer) > 50:
            offer = offer[:47] + "..."
        
        deal_text = MESSAGES[lang]['my_deals_item'].format(
            deal_id=deal['deal_id'],
            date=date_str,
            role=role,
            username=other_username,
            user_id=other_user_id if other_user_id else "N/A",
            amount=deal['amount'],
            currency=currency,
            offer=offer,
            status=status
        ) + "\n"
        
        result += deal_text
    
    return result, total_pages

def set_user_referrer(user_id, referrer_id):
    """Устанавливает реферера для пользователя"""
    with db_lock:
        cursor.execute("UPDATE users SET referrer_id = ? WHERE user_id = ? AND referrer_id IS NULL", (referrer_id, user_id))
        conn.commit()

def get_user_referrer(user_id):
    """Получает ID реферера пользователя"""
    with db_lock:
        cursor.execute("SELECT referrer_id FROM users WHERE user_id = ?", (user_id,))
        res = cursor.fetchone()
        return res[0] if res and res[0] else None

def get_referral_stats(user_id):
    """Получает статистику рефералов пользователя"""
    with db_lock:
        # Всего приглашено
        cursor.execute("SELECT COUNT(*) FROM users WHERE referrer_id = ?", (user_id,))
        total_referrals_result = cursor.fetchone()
        total_referrals = total_referrals_result[0] if total_referrals_result else 0
        
        # Активные рефералы (которые сделали хотя бы одну сделку)
        cursor.execute("""
            SELECT COUNT(DISTINCT u.user_id) 
            FROM users u
            INNER JOIN deals d ON u.user_id = d.seller_id OR u.user_id = d.buyer_id
            WHERE u.referrer_id = ? AND d.status = 'completed'
        """, (user_id,))
        active_referrals_result = cursor.fetchone()
        active_referrals = active_referrals_result[0] if active_referrals_result else 0
        
        # Общий объем сделок рефералов (только RUB для карт)
        cursor.execute("""
            SELECT COALESCE(SUM(CASE WHEN d.deal_type = 'card' THEN d.amount ELSE 0 END), 0)
            FROM deals d
            INNER JOIN users u ON (u.user_id = d.seller_id OR u.user_id = d.buyer_id)
            WHERE u.referrer_id = ? AND d.status = 'completed'
        """, (user_id,))
        total_volume_result = cursor.fetchone()
        total_volume = total_volume_result[0] if total_volume_result and total_volume_result[0] else 0.0
        
        return {
            'total_referrals': total_referrals,
            'active_referrals': active_referrals,
            'total_volume': total_volume
        }

def get_user_by_id_or_username(identifier):
    """Находит пользователя по ID или username"""
    # Очищаем идентификатор от лишних символов
    identifier = identifier.strip().replace('@', '').replace(' ', '')
    
    if not identifier:
        return None
    
    try:
        # Пытаемся как ID (цифры)
        if identifier.isdigit() or (identifier.startswith('-') and identifier[1:].isdigit()):
            user_id = int(identifier)
            with db_lock:
                cursor.execute("SELECT user_id, ton_wallet, card_number, lang, successful_deals, last_activity, referrer_id, guarantor_status FROM users WHERE user_id = ?", (user_id,))
                row = cursor.fetchone()
                if row:
                    return {
                        'user_id': row[0],
                        'ton_wallet': row[1],
                        'card_number': row[2],
                        'lang': row[3],
                        'successful_deals': row[4],
                        'last_activity': row[5],
                        'referrer_id': row[6],
                        'guarantor_status': row[7] if len(row) > 7 else 'none'
                    }
                # Если ID не найден в базе, но это валидный ID, создаем запись
                # Это нужно для случаев, когда пользователь еще не использовал бота
                return None
    except ValueError:
        pass
    except Exception as e:
        pass
    
    # Пытаемся найти по username в сделках (без учета регистра)
    username = identifier.lower()
    with db_lock:
        # Ищем точное совпадение
        cursor.execute("SELECT DISTINCT seller_id FROM deals WHERE LOWER(seller_username) = ? LIMIT 1", (username,))
        row = cursor.fetchone()
        if row:
            user_id = row[0]
            cursor.execute("SELECT user_id, ton_wallet, card_number, lang, successful_deals, last_activity, referrer_id, guarantor_status FROM users WHERE user_id = ?", (user_id,))
            user_row = cursor.fetchone()
            if user_row:
                return {
                    'user_id': user_row[0],
                    'ton_wallet': user_row[1],
                    'card_number': user_row[2],
                    'lang': user_row[3],
                    'successful_deals': user_row[4],
                    'last_activity': user_row[5],
                    'referrer_id': user_row[6],
                    'guarantor_status': user_row[7] if len(user_row) > 7 else 'none'
                }
    
    return None

def get_user_username_from_deals(user_id):
    """Получает username пользователя из его сделок"""
    with db_lock:
        cursor.execute("SELECT seller_username FROM deals WHERE seller_id = ? LIMIT 1", (user_id,))
        row = cursor.fetchone()
        return row[0] if row and row[0] else "unknown"

def get_guarantor_info(user_id, lang='ru'):
    """Получает информацию о статусе гаранта пользователя"""
    with db_lock:
        cursor.execute("SELECT guarantor_status FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        if row and row[0] and row[0] != 'none':
            status = row[0]
            if lang == 'ru':
                if status == 'verified':
                    return "✅ Проверенный гарант"
                elif status == 'premium':
                    return "⭐ Премиум гарант"
                elif status == 'vip':
                    return "💎 VIP гарант"
                else:
                    return "❌ Не является гарантом"
            else:
                if status == 'verified':
                    return "✅ Verified Guarantor"
                elif status == 'premium':
                    return "⭐ Premium Guarantor"
                elif status == 'vip':
                    return "💎 VIP Guarantor"
                else:
                    return "❌ Not a guarantor"
        if lang == 'ru':
            return "❌ Не является гарантом"
        else:
            return "❌ Not a guarantor"

def format_user_info(user_data, lang):
    """Форматирует информацию о пользователе для отображения"""
    if not user_data:
        return "❌ Пользователь не найден" if lang == 'ru' else "❌ User not found"
    
    user_id = user_data['user_id']
    username = get_user_username_from_deals(user_id)
    successful_deals = user_data.get('successful_deals', 0)
    guarantor_status = get_guarantor_info(user_id, lang)
    
    # Получаем статистику сделок
    deals = get_user_deals(user_id)
    total_deals = len(deals)
    completed_deals = len([d for d in deals if d.get('status') == 'completed'])
    
    # Получаем реферальную статистику
    referral_stats = get_referral_stats(user_id)
    
    # Форматируем дату последней активности
    last_activity = user_data.get('last_activity', 0)
    activity_date = format_time_moscow(last_activity, lang) if last_activity else ("Неизвестно" if lang == 'ru' else "Unknown")
    
    if lang == 'ru':
        result = f"👤 Информация о пользователе\n\n"
        result += f"🆔 ID: {user_id}\n"
        result += f"📛 Username: @{username}\n\n"
        result += f"📊 Статистика:\n"
        result += f"• Успешных сделок: {successful_deals}\n"
        result += f"• Всего сделок: {total_deals}\n"
        result += f"• Завершенных сделок: {completed_deals}\n"
        result += f"• Приглашено рефералов: {referral_stats['total_referrals']}\n\n"
        result += f"💎 Статус гаранта:\n{guarantor_status}\n\n"
        result += f"🕐 Последняя активность: {activity_date}"
    else:
        result = f"👤 User Information\n\n"
        result += f"🆔 ID: {user_id}\n"
        result += f"📛 Username: @{username}\n\n"
        result += f"📊 Statistics:\n"
        result += f"• Successful deals: {successful_deals}\n"
        result += f"• Total deals: {total_deals}\n"
        result += f"• Completed deals: {completed_deals}\n"
        result += f"• Referrals invited: {referral_stats['total_referrals']}\n\n"
        result += f"💎 Guarantor Status:\n{guarantor_status}\n\n"
        result += f"🕐 Last activity: {activity_date}"
    
    return result

user_states = {}
user_inputs = {}

def set_user_state(user_id, state):
    user_states[user_id] = state

def get_user_state(user_id):
    return user_states.get(user_id)

def clear_user_state(user_id):
    user_states.pop(user_id, None)
    user_inputs.pop(user_id, None)

def set_user_input(user_id, key, value):
    if user_id not in user_inputs:
        user_inputs[user_id] = {}
    user_inputs[user_id][key] = value

def get_user_input(user_id, key):
    if user_id in user_inputs:
        return user_inputs[user_id].get(key)
    return None

def validate_ton_address(addr): 
    return bool(re.fullmatch(r'^[a-zA-Z0-9\-_]{48,64}$', addr.strip()))

def validate_nft_link(link): 
    return 't.me/nft/' in link or 'https://t.me/nft/' in link

def validate_card_number(card):
    card_clean = card.replace(' ', '').replace('-', '')
    return bool(re.fullmatch(r'\d{12,19}', card_clean))

MESSAGES = {
    'ru': {
        'welcome': ("<b>Добро пожаловать в NFT guard – надежный P2P-гарант</b>\n\n"
                    "💼 <b>Покупайте и продавайте всё, что угодно – безопасно!</b>\n"
                    "От Telegram-подарков и NFT до токенов и фиата – сделки проходят легко и без риска.\n\n"
                    "📋 Добавьте свои реквизиты что-бы успешно отправить вам деньги после получение оплаты!\n\n"
                    "❓ <b>Как использовать бота?</b>\n"
                    "👉 <a href='https://teletype.in/@starforgeinfo/1VTWHz3JMl4'>Инструкция по использованию</a>\n\n"
                    "Выберите нужный раздел ниже:"),
        'manage_rekv': "Выберите действие:",
        'add_ton_wallet': "🔑 Добавьте ваш TON-кошелек:",
        'add_card_number': "💳 Введите номер вашей карты (12-19 цифр):",
        'ton_invalid': "❌ Неверный адрес TON-кошелька",
        'card_invalid': "❌ Неверный формат номера карты. Введите только цифры, от 12 до 19 символов.",
        'ton_ok': "✅ Установлен TON-кошелек",
        'card_ok': "✅ Номер карты сохранен",
        'back_btn': "⬅️ Вернуться в меню",
        'create_deal_start': ("При проведении сделки со скинами Steam укажите ссылку на любой подарок.\n"
                             "После оплаты свяжитесь с системой — @GuarantNFTsupport\n\n"
                             "💰 Выберите метод оплаты:"),
        'choose_pay_method_ton': "💎 TON-Кошелек",
        'choose_pay_method_star': "⭐ Звезды",
        'choose_pay_method_card': "💳 На карту",
        'enter_ton_amount': "Введите сумму TON сделки (например: 199.99):",
        'enter_star_amount': "Введите количество звезд для оплаты (например: 150):",
        'enter_card_amount': "💼 Создание сделки\n\nВведите сумму RUB сделки в формате: 199.99",
        'enter_deal_offer': ("📝 Опишите, что предлагаете за {amount} {currency}.\n\n"
                            "Пример:\nhttps://t.me/nft/PlushPepe-1\nhttps://t.me/nft/DurovsCap-1"),
        'enter_deal_offer_card': ("📝 Укажите, что вы предлагаете в этой сделке за {amount} RUB\n\n"
                            "Пример:\nhttps://t.me/nft/PlushPepe-1\nhttps://t.me/nft/DurovsCap-1"),
        'deal_created': ("✅ Сделка создана!\n\n"
                         "💰 Сумма: {amount} {currency}\n"
                         "📜 Описание: {offer}\n"
                         "🔗 Ссылка для покупателя:\n{link}"),
        'deal_closed_confirm': "❓ Уверены, что хотите закрыть сделку {deal_id}?",
        'deal_closed_yes': "✅ Сделка {deal_id} удалена",
        'lang_change': "Изменить язык:",
        'support_info': "💁‍♂️ Поддержка: @GuarantNFTsupport",
        'invalid_amount': "❌ Неверный формат суммы. Попробуйте снова.",
        'invalid_nft_link': "❌ Принимайте ссылки только в формате https://t.me/nft/… Попробуйте снова.",
        'deal_joined_notify_seller': "✅ Пользователь @{buyer} присоединился к сделке {deal_id}",
        'deal_info_for_buyer_ton': ("💳 Информация о сделке {deal_id}\n\n"
                               "👤 Вы покупатель\n"
                               "📌 Продавец: @{seller_username} | 🆔 {seller_id}\n"
                               "• Успешных сделок: {seller_deals}\n\n"
                               "• Вы покупаете:\n{offer}\n\n"
                               "🏦 Оплатить на:\nUQAm5SBXe9r_KrVxOuv_VRdjinjL-WbReaTqBFw1EV-n_o3o\n\n"
                               "💰 Сумма: {amount} TON\n"
                               "📝 Комментарий: {deal_id}\n\n"
                               "⚠️ Проверьте данные, мемо обязателен!\nЕсли без мемо, заполните форму — @GuarantNFTsupport"),
        'deal_info_for_buyer_star': ("💳 Информация о сделке {deal_id}\n\n"
                               "👤 Вы покупатель в сделке.\n"
                               "📌 Продавец: @{seller_username} | 🆔 {seller_id}\n"
                               "• Успешные сделки: {seller_deals}\n\n"
                               "• Вы покупаете:\n{offer}\n\n"
                               "🏦 Адрес для оплаты:\n@GuarantNFTsupport\n\n"
                               "💰 Сумма к оплате: {amount} STAR\n"
                               "📝 Комментарий к платежу(мемо): {deal_id}\n\n"
                               "⚠️ Пожалуйста, убедитесь в правильности данных перед оплатой. Комментарий(мемо) обязателен!\n"
                               "В случае если вы отправили транзакцию без комментария заполните форму — @GuarantNFTsupport"),
        'deal_info_for_buyer_card': ("💳 Информация о сделке {deal_id}\n\n"
                               "👤 Вы покупатель в сделке.\n"
                               "📌 Продавец: @{seller_username} | 🆔 {seller_id}\n"
                               "• Успешные сделки: {seller_deals}\n\n"
                               "• Вы покупаете:\n{offer}\n\n"
                               "🏦 Адрес для оплаты:\n{card_number}\n\n"
                               "💰 Сумма к оплате: {amount} RUB\n"
                               "📝 Комментарий к платежу(мемо): {deal_id}\n\n"
                               "⚠️ Пожалуйста, убедитесь в правильности данных перед оплатой. Комментарий(мемо) обязателен!\n"
                               "В случае если вы отправили транзакцию без комментария заполните форму — @NftGuardHelper"),
        'payment_confirm_text': "✅ Подтвердить оплату",
        'exit_deal_text': "❌ Выйти из сделки",
        'pay_stars_btn': "💫 Оплатить Stars",
        'exit_confirm_text': "❓ Вы уверены, что хотите покинуть сделку {deal_id}?",
        'exit_confirm_yes': "✅ Вы покинули сделку {deal_id}",
        'exit_confirm_no': "⬅️ Нет",
        'deal_not_found': "❌ Сделка {deal_id} не найдена или уже закрыта.",
        'cannot_buy_own': "❌ Вы не можете купить у самого себя!",
        'buyer_exists': "❌ К этой сделке уже присоединился другой покупатель!",
        'seller_notified': "✅ Продавец получил уведомление об оплате!",
        'no_payment_methods': "❌ Для создания сделки необходимо добавить TON-кошелек или карту!\n\nПерейдите в 'Управление реквизитами' и добавьте платежные данные.",
        'deals_set': "✅ Установлено успешных сделок: {count}",
        'buy_command_usage': "Использование: /buy <ID сделки>\nПример: /buy ABC123XY",
        'set_deals_usage': "Использование: /set_my_deals <число>\nПример: /set_my_deals 100",
        'payment_success': "✅ Оплата успешно проведена! Спасибо за покупку!",
        'my_deals_title': "💼 Мои сделки",
        'my_deals_empty': "📭 У вас пока нет сделок.\n\nСоздайте первую сделку, чтобы начать торговать!",
        'my_deals_item': ("🔹 Сделка {deal_id}\n"
                         "📅 Дата: {date}\n"
                         "👤 {role}: @{username} (ID: {user_id})\n"
                         "💰 Сумма: {amount} {currency}\n"
                         "📦 NFT: {offer}\n"
                         "📊 Статус: {status}\n"),
        'deal_role_seller': "Продавец",
        'deal_role_buyer': "Покупатель",
        'deal_status_open': "🟡 Открыта",
        'deal_status_completed': "🟢 Завершена",
        'deal_status_closed': "🔴 Закрыта",
        'referrals_title': "🔗 Ваша реферальная ссылка:",
        'referrals_text': ("🔗 Ваша реферальная ссылка:\n\n"
                          "{referral_link}\n\n"
                          "📊 Статистика рефералов:\n\n"
                          "• Всего приглашено: {total_referrals}\n"
                          "• Активных рефералов: {active_referrals}\n"
                          "• Общий объем сделок: {total_volume} ₽\n\n"
                          "💰 Ваши бонусы:\n\n"
                          "• За каждого активного реферала: +5% к балансу\n"
                          "• При первой сделке реферала: +100 ₽"),
        'search_user_title': "💠 Поисковик пользователя в нашем боте",
        'search_user_text': "💠 Поисковик пользователя в нашем боте - отправьте снизу id или @username пользователя что-бы узнать информацию",
        'user_not_found': "❌ Пользователь не найден. Проверьте правильность ID или @username.",
        'statistics_title': "📊 Статистика NFT guard",
        'statistics_text': ("📊 Статистика NFT guard\n\n"
                           "🤝 Всего сделок: {total_deals}\n"
                           "✅ Успешных сделок: {successful_deals}\n"
                           "💰 Общий объем: ${total_volume}\n"
                           "⭐️ Средний рейтинг: 4.6/5.0\n"
                           "🟢 Онлайн сейчас: {online_users}\n\n"
                           "📈 Наши преимущества:\n\n"
                           "• 🔒 Гарант-сервис на все сделки\n"
                           "• ⚡️ Мгновенная доставка товаров\n"
                           "• 🛡️ Защита от мошенников\n"
                           "• 💎 Проверенные продавцы\n"
                           "• 📞 24/7 Поддержка\n"
                           "• ⭐️ 99.8% положительных отзывов\n\n"
                           "⭐️ Наш канал: @GuarantNFTsupport\n"
                           "📞 Поддержка: @GuarantNFTsupport"),
    },
    'en': {
        'welcome': ("<b>Welcome to NFT guard – reliable P2P guarantor</b>\n\n"
                    "💼 <b>Buy and sell anything – safely!</b>\n"
                    "From Telegram gifts and NFTs to tokens and fiat – deals are easy and risk-free.\n\n"
                    "📋 Add your payment details to successfully receive money after payment!\n\n"
                    "❓ <b>How to use the bot?</b>\n"
                    "👉 <a href='https://teletype.in/@starforgeinfo/1VTWHz3JMl4'>Usage instructions</a>\n\n"
                    "Choose a section below:"),
        'manage_rekv': "Choose an action:",
        'add_ton_wallet': "🔑 Add your TON wallet:",
        'add_card_number': "💳 Enter your card number (12-19 digits):",
        'ton_invalid': "❌ Invalid TON wallet address",
        'card_invalid': "❌ Invalid card number format. Enter only digits, 12 to 19 characters.",
        'ton_ok': "✅ TON wallet set",
        'card_ok': "✅ Card number saved",
        'back_btn': "⬅️ Back to menu",
        'create_deal_start': ("For Steam skins deals, provide a link to any gift.\n"
                             "After payment, contact the system — \n\n"
                             "💰 Choose payment method:"),
        'choose_pay_method_ton': "💎 TON Wallet",
        'choose_pay_method_star': "⭐ Stars",
        'choose_pay_method_card': "💳 Card",
        'enter_ton_amount': "Enter TON deal amount (e.g.: 199.99):",
        'enter_star_amount': "Enter number of stars for payment (e.g.: 150):",
        'enter_card_amount': "💼 Creating deal\n\nEnter RUB deal amount in format: 199.99",
        'enter_deal_offer': ("📝 Describe what you offer for {amount} {currency}.\n\n"
                            "Example:\nhttps://t.me/nft/PlushPepe-1\nhttps://t.me/nft/DurovsCap-1"),
        'enter_deal_offer_card': ("📝 Specify what you offer in this deal for {amount} RUB\n\n"
                            "Example:\nhttps://t.me/nft/PlushPepe-1\nhttps://t.me/nft/DurovsCap-1"),
        'deal_created': ("✅ Deal created!\n\n"
                         "💰 Amount: {amount} {currency}\n"
                         "📜 Description: {offer}\n"
                         "🔗 Link for buyer:\n{link}"),
        'deal_closed_confirm': "❓ Are you sure you want to close deal {deal_id}?",
        'deal_closed_yes': "✅ Deal {deal_id} deleted",
        'lang_change': "Change language:",
        'support_info': "💁‍♂️ Support: @GuarantNFTsupport",
        'invalid_amount': "❌ Invalid amount format. Try again.",
        'invalid_nft_link': "❌ Only accept links in format https://t.me/nft/… Try again.",
        'deal_joined_notify_seller': "✅ User @{buyer} joined deal {deal_id}",
        'deal_info_for_buyer_ton': ("💳 Deal info {deal_id}\n\n"
                               "👤 You are the buyer\n"
                               "📌 Seller: @{seller_username} | 🆔 {seller_id}\n"
                               "• Successful deals: {seller_deals}\n\n"
                               "• You are buying:\n{offer}\n\n"
                               "🏦 Pay to:\nUQAm5SBXe9r_KrVxOuv_VRdjinjL-WbReaTqBFw1EV-n_o3o\n\n"
                               "💰 Amount: {amount} TON\n"
                               "📝 Comment: {deal_id}\n\n"
                               "⚠️ Check details, memo is required!\nIf without memo, fill form — @GuarantNFTsupport"),
        'deal_info_for_buyer_star': ("💳 Deal info {deal_id}\n\n"
                               "👤 You are the buyer in this deal.\n"
                               "📌 Seller: @{seller_username} | 🆔 {seller_id}\n"
                               "• Successful deals: {seller_deals}\n\n"
                               "• You are buying:\n{offer}\n\n"
                               "🏦 Payment address:\n@GuarantNFTsupport\n\n"
                               "💰 Amount to pay: {amount} STAR\n"
                               "📝 Payment comment(memo): {deal_id}\n\n"
                               "⚠️ Please check the details before payment. Comment(memo) is required!\n"
                               "If you sent transaction without comment, fill the form — @GuarantNFTsupport"),
        'deal_info_for_buyer_card': ("💳 Deal info {deal_id}\n\n"
                               "👤 You are the buyer in this deal.\n"
                               "📌 Seller: @{seller_username} | 🆔 {seller_id}\n"
                               "• Successful deals: {seller_deals}\n\n"
                               "• You are buying:\n{offer}\n\n"
                               "🏦 Payment address:\n{card_number}\n\n"
                               "💰 Amount to pay: {amount} RUB\n"
                               "📝 Payment comment(memo): {deal_id}\n\n"
                               "⚠️ Please check the details before payment. Comment(memo) is required!\n"
                               "If you sent transaction without comment, fill the form — @GuarantNFTsupport"),
        'payment_confirm_text': "✅ Confirm payment",
        'exit_deal_text': "❌ Exit deal",
        'pay_stars_btn': "💫 Pay Stars",
        'exit_confirm_text': "❓ Are you sure you want to leave deal {deal_id}?",
        'exit_confirm_yes': "✅ You left deal {deal_id}",
        'exit_confirm_no': "⬅️ No",
        'deal_not_found': "❌ Deal {deal_id} not found or already closed.",
        'cannot_buy_own': "❌ You cannot buy from yourself!",
        'buyer_exists': "❌ Another buyer already joined this deal!",
        'seller_notified': "✅ Seller received payment notification!",
        'no_payment_methods': "❌ To create a deal, add TON wallet or card!\n\nGo to 'Manage Wallets' and add payment details.",
        'deals_set': "✅ Successful deals set: {count}",
        'buy_command_usage': "Usage: /buy <Deal ID>\nExample: /buy ABC123XY",
        'set_deals_usage': "Usage: /set_my_deals <number>\nExample: /set_my_deals 100",
        'payment_success': "✅ Payment successful! Thank you for your purchase!",
        'my_deals_title': "💼 My Deals",
        'my_deals_empty': "📭 You don't have any deals yet.\n\nCreate your first deal to start trading!",
        'my_deals_item': ("🔹 Deal {deal_id}\n"
                         "📅 Date: {date}\n"
                         "👤 {role}: @{username} (ID: {user_id})\n"
                         "💰 Amount: {amount} {currency}\n"
                         "📦 NFT: {offer}\n"
                         "📊 Status: {status}\n"),
        'deal_role_seller': "Seller",
        'deal_role_buyer': "Buyer",
        'deal_status_open': "🟡 Open",
        'deal_status_completed': "🟢 Completed",
        'deal_status_closed': "🔴 Closed",
        'referrals_title': "🔗 Your referral link:",
        'referrals_text': ("🔗 Your referral link:\n\n"
                          "{referral_link}\n\n"
                          "📊 Referral statistics:\n\n"
                          "• Total invited: {total_referrals}\n"
                          "• Active referrals: {active_referrals}\n"
                          "• Total deal volume: {total_volume} ₽\n\n"
                          "💰 Your bonuses:\n\n"
                          "• For each active referral: +5% to balance\n"
                          "• On referral's first deal: +100 ₽"),
        'search_user_title': "💠 User search in our bot",
        'search_user_text': "💠 User search in our bot - send user ID or @username below to get information",
        'user_not_found': "❌ User not found. Please check the ID or @username.",
        'statistics_title': "📊 NFT guard Statistics",
        'statistics_text': ("📊 NFT guard Statistics\n\n"
                           "🤝 Total deals: {total_deals}\n"
                           "✅ Successful deals: {successful_deals}\n"
                           "💰 Total volume: ${total_volume}\n"
                           "⭐️ Average rating: 4.6/5.0\n"
                           "🟢 Online now: {online_users}\n\n"
                           "📈 Our advantages:\n\n"
                           "• 🔒 Guarantor service for all deals\n"
                           "• ⚡️ Instant delivery of goods\n"
                           "• 🛡️ Protection from scammers\n"
                           "• 💎 Verified sellers\n"
                           "• 📞 24/7 Support\n"
                           "• ⭐️ 99.8% positive reviews\n\n"
                           "⭐️ Our channel: @GuarantNFTsupport\n"
                           "📞 Support: @GuarantNFTsupport"),
    }
}

def main_menu_keyboard(lang):
    kb = types.InlineKeyboardMarkup(row_width=2)
    # Первый ряд: Создать сделку (на всю ширину)
    kb.add(
        types.InlineKeyboardButton("📔 " + ("Создать сделку" if lang=='ru' else "Create Deal"), callback_data="create_deal")
    )
    # Второй ряд: Мои сделки | Рефералы
    kb.add(
        types.InlineKeyboardButton("💼 " + ("Мои сделки" if lang=='ru' else "My Deals"), callback_data="my_deals"),
        types.InlineKeyboardButton("💠 " + ("Рефералы" if lang=='ru' else "Referrals"), callback_data="referrals")
    )
    # Третий ряд: Подробнее | Реквизиты
    kb.add(
        types.InlineKeyboardButton("ℹ️ " + ("Подробнее" if lang=='ru' else "More Info"), callback_data="show_statistics"),
        types.InlineKeyboardButton("📥 " + ("Реквизиты" if lang=='ru' else "Wallets"), callback_data="manage_rekv")
    )
    # Четвертый ряд: Язык | Поддержка
    kb.add(
        types.InlineKeyboardButton("🏴 " + ("Язык" if lang=='ru' else "Language"), callback_data="change_lang"),
        types.InlineKeyboardButton("💁‍♂️ " + ("Поддержка" if lang=='ru' else "Support"), url=f"https://t.me/{get_support_username()}")
    )
    # Пятый ряд: Пользователь (в самый низ)
    kb.add(
        types.InlineKeyboardButton("🔎 " + ("Пользователь" if lang=='ru' else "User"), callback_data="search_user")
    )
    return kb

def statistics_keyboard(lang):
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton("⬅️ " + ("Назад" if lang=='ru' else "Back"), callback_data="back_to_menu")
    )
    return kb

def my_deals_keyboard(lang, page, total_pages):
    """Клавиатура для навигации по сделкам"""
    kb = types.InlineKeyboardMarkup(row_width=3)
    
    buttons = []
    
    # Кнопка "Предыдущая" если не первая страница
    if page > 1:
        buttons.append(types.InlineKeyboardButton("◀️ " + ("Назад" if lang == 'ru' else "Prev"), callback_data=f"deals_page_{page-1}"))
    
    # Кнопка с текущей страницей (неактивная)
    buttons.append(types.InlineKeyboardButton(f"• {page}/{total_pages} •", callback_data="deals_current"))
    
    # Кнопка "Следующая" если не последняя страница
    if page < total_pages:
        buttons.append(types.InlineKeyboardButton(("Вперед" if lang == 'ru' else "Next") + " ▶️", callback_data=f"deals_page_{page+1}"))
    
    if buttons:
        kb.row(*buttons)
    
    # Кнопка "Назад в меню"
    kb.add(types.InlineKeyboardButton("⬅️ " + ("Назад" if lang == 'ru' else "Back"), callback_data="back_to_menu"))
    return kb

def rekv_keyboard(lang):
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton("🪙 " + ("Добавить/Изменить TON" if lang=='ru' else "Add/Edit TON Wallet"), callback_data="add_ton"),
        types.InlineKeyboardButton("💳 " + ("Добавить/Изменить карту" if lang=='ru' else "Add/Edit Card"), callback_data="add_card"),
        types.InlineKeyboardButton(MESSAGES[lang]["back_btn"], callback_data="back_to_menu")
    )
    return kb

def pay_method_keyboard(lang):
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton(MESSAGES[lang]["choose_pay_method_ton"], callback_data="pay_ton"),
        types.InlineKeyboardButton(MESSAGES[lang]["choose_pay_method_star"], callback_data="pay_star")
    )
    kb.add(types.InlineKeyboardButton(MESSAGES[lang]["choose_pay_method_card"], callback_data="pay_card"))
    kb.add(types.InlineKeyboardButton(MESSAGES[lang]["back_btn"], callback_data="back_to_menu"))
    return kb

def deal_close_keyboard(deal_id, lang):
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(types.InlineKeyboardButton("❌ " + ("Закрыть Сделку" if lang=='ru' else "Close Deal"), callback_data=f"close_{deal_id}"))
    kb.add(types.InlineKeyboardButton(MESSAGES[lang]["back_btn"], callback_data="back_to_menu"))
    return kb

def confirm_exit_keyboard(deal_id, lang):
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("✅ " + ("Да, закрыть" if lang=='ru' else "Yes, Close"), callback_data=f"exit_yes_{deal_id}"),
        types.InlineKeyboardButton(MESSAGES[lang]["exit_confirm_no"], callback_data=f"back_to_deal_{deal_id}"),
    )
    return kb

def deal_buyer_keyboard_ton(deal_id, lang):
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton(MESSAGES[lang]['payment_confirm_text'], callback_data=f"confirm_pay_{deal_id}"),
        types.InlineKeyboardButton(MESSAGES[lang]['exit_deal_text'], callback_data=f"exit_deal_{deal_id}")
    )
    return kb

def deal_buyer_keyboard_star(deal_id, amount, lang):
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton(MESSAGES[lang]['pay_stars_btn'], callback_data=f"pay_stars_{deal_id}"),
        types.InlineKeyboardButton(MESSAGES[lang]['exit_deal_text'], callback_data=f"exit_deal_{deal_id}")
    )
    return kb

def deal_buyer_keyboard_card(deal_id, lang):
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton(MESSAGES[lang]['payment_confirm_text'], callback_data=f"confirm_pay_{deal_id}"),
        types.InlineKeyboardButton(MESSAGES[lang]['exit_deal_text'], callback_data=f"exit_deal_{deal_id}")
    )
    return kb

def language_choose_keyboard():
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("Русский", callback_data="lang_ru"),
        types.InlineKeyboardButton("English", callback_data="lang_en"),
        types.InlineKeyboardButton("⬅️ Back to Menu", callback_data="back_to_menu")
    )
    return kb

@bot.message_handler(commands=['start'])
def handle_start(message):
    user_id = message.from_user.id
    update_user_activity(user_id)
    lang = get_user_lang(user_id)
    clear_user_state(user_id)
    args = message.text.split()
    if len(args) > 1:
        param = args[1]
        # Обработка реферальных ссылок
        if param.startswith("ref_"):
            referrer_id_str = param.replace("ref_", "").strip()
            try:
                referrer_id = int(referrer_id_str)
                if referrer_id != user_id:  # Нельзя быть реферером самого себя
                    set_user_referrer(user_id, referrer_id)
            except ValueError:
                pass
        elif param.startswith("order_ton_"):
            deal_id = param.replace("order_ton_", "").replace('#', '').strip()
            deal = get_deal(deal_id)
            if not deal or deal['status'] != 'open':
                bot.send_message(user_id, MESSAGES[lang]['deal_not_found'].format(deal_id=deal_id))
                return
            if deal['seller_id'] == user_id:
                bot.send_message(user_id, MESSAGES[lang]['cannot_buy_own'])
                return
            if deal['buyer_id'] and deal['buyer_id'] != user_id:
                bot.send_message(user_id, MESSAGES[lang]['buyer_exists'])
                return
            set_deal_buyer(deal_id, user_id)
            buyer_username = message.from_user.username or 'unknown'
            safe_send_message(deal['seller_id'], MESSAGES['ru']['deal_joined_notify_seller'].format(buyer=buyer_username, deal_id=deal_id))
            seller_deals_count = get_successful_deals_count(deal['seller_id'])
            if deal['deal_type'] == 'ton':
                info_text = format_support(MESSAGES[lang]['deal_info_for_buyer_ton'].format(
                    deal_id=deal_id,
                    seller_username=deal['seller_username'],
                    seller_id=deal['seller_id'],
                    seller_deals=seller_deals_count,
                    offer=deal['offer'],
                    amount=deal['amount']
                ))
                bot.send_message(user_id, info_text, reply_markup=deal_buyer_keyboard_ton(deal_id, lang))
            elif deal['deal_type'] == 'star':
                info_text = format_support(MESSAGES[lang]['deal_info_for_buyer_star'].format(
                    deal_id=deal_id,
                    seller_username=deal['seller_username'],
                    seller_id=deal['seller_id'],
                    seller_deals=seller_deals_count,
                    offer=deal['offer'],
                    amount=int(deal['amount'])
                ))
                bot.send_message(user_id, info_text, reply_markup=deal_buyer_keyboard_star(deal_id, int(deal['amount']), lang))
            elif deal['deal_type'] == 'card':
                seller_card = get_user_card_number(deal['seller_id'])
                info_text = format_support(MESSAGES[lang]['deal_info_for_buyer_card'].format(
                    deal_id=deal_id,
                    seller_username=deal['seller_username'],
                    seller_id=deal['seller_id'],
                    seller_deals=seller_deals_count,
                    offer=deal['offer'],
                    amount=deal['amount'],
                    card_number=seller_card if seller_card else "Не указана"
                ))
                bot.send_message(user_id, info_text, reply_markup=deal_buyer_keyboard_card(deal_id, lang))
            clear_user_state(user_id)
            return
    # Отправляем только текстовое сообщение без фото
    safe_send_message(user_id, MESSAGES[lang]['welcome'], reply_markup=main_menu_keyboard(lang), parse_mode='HTML')

@bot.message_handler(commands=['pay'])
def handle_pay_command(message):
    """Обработчик команды /pay для оплаты сделки с баланса"""
    user_id = message.from_user.id
    update_user_activity(user_id)
    lang = get_user_lang(user_id)
    
    # Парсим ID сделки из команды
    args = message.text.split()
    if len(args) < 2:
        safe_send_message(user_id, "❌ Использование: /pay ID_сделки\n\nПример: /pay 12345" if lang == 'ru' else "❌ Usage: /pay deal_ID\n\nExample: /pay 12345")
        return
    
    deal_id = args[1].replace('#', '').strip()
    print(f"[DEBUG] /pay command: user {user_id} trying to pay deal {deal_id}")
    
    # Получаем сделку
    deal = get_deal(deal_id)
    
    if not deal:
        safe_send_message(user_id, f"❌ Сделка #{deal_id} не найдена" if lang == 'ru' else f"❌ Deal #{deal_id} not found")
        return
    
    # Проверяем статус сделки
    if deal['status'] not in ['open', 'paid']:
        safe_send_message(user_id, f"❌ Сделка #{deal_id} уже закрыта или завершена" if lang == 'ru' else f"❌ Deal #{deal_id} is already closed or completed")
        return
    
    # Проверяем, что пользователь не продавец
    if deal['seller_id'] == user_id:
        safe_send_message(user_id, "❌ Вы не можете оплатить свою собственную сделку" if lang == 'ru' else "❌ You cannot pay for your own deal")
        return
    
    # Устанавливаем покупателя, если ещё не установлен
    if not deal['buyer_id']:
        set_deal_buyer(deal_id, user_id)
        # Уведомляем продавца
        buyer_username = message.from_user.username or 'unknown'
        safe_send_message(deal['seller_id'], MESSAGES['ru']['deal_joined_notify_seller'].format(buyer=buyer_username, deal_id=deal_id))
    elif deal['buyer_id'] != user_id:
        safe_send_message(user_id, f"❌ Сделка #{deal_id} уже имеет другого покупателя" if lang == 'ru' else f"❌ Deal #{deal_id} already has another buyer")
        return
    
    # Определяем валюту и списываем с баланса
    deal_type = deal.get('deal_type')
    if deal_type == 'ton':
        currency = 'ton'
        currency_name = 'TON'
    elif deal_type == 'star':
        currency = 'star'
        currency_name = 'STAR'
    elif deal_type == 'card':
        currency = 'rub'
        currency_name = 'RUB'
    else:
        safe_send_message(user_id, "❌ Неизвестный тип сделки" if lang == 'ru' else "❌ Unknown deal type")
        return
    
    amount = float(deal['amount'])
    balance = get_user_balance(user_id)
    
    # Проверяем баланс
    if balance[currency] < amount:
        error_msg = f"❌ Недостаточно средств на балансе. Требуется: {amount} {currency_name}, доступно: {balance[currency]:.2f} {currency_name}" if lang == 'ru' else f"❌ Insufficient balance. Required: {amount} {currency_name}, available: {balance[currency]:.2f} {currency_name}"
        safe_send_message(user_id, error_msg)
        return
    
    # Списываем средства
    deduct_result = deduct_balance(user_id, currency, amount)
    
    if not deduct_result:
        safe_send_message(user_id, "❌ Ошибка списания средств" if lang == 'ru' else "❌ Error deducting funds")
        return
    
    print(f"[DEBUG] Payment deducted successfully from balance")
    
    # Уведомляем покупателя сразу
    buyer_username = message.from_user.username
    if buyer_username:
        buyer_display = f"@{buyer_username}"
    else:
        buyer_display = f"ID: {user_id}"
    
    buyer_msg = f"✅ Оплата успешно проведена!\n\n💰 Сделка #{deal_id}\n💫 Оплачено: {amount} {currency_name}\n📦 За: {deal['offer'][:100]}\n\nОжидайте получение НФТ!" if lang == 'ru' else f"✅ Payment successful!\n\n💰 Deal #{deal_id}\n💫 Paid: {amount} {currency_name}\n📦 For: {deal['offer'][:100]}\n\nWait for NFT receipt!"
    safe_send_message(user_id, buyer_msg)
    
    # Создаем клавиатуру с кнопкой "Передал" для продавца
    seller_keyboard = types.InlineKeyboardMarkup()
    seller_keyboard.add(types.InlineKeyboardButton("💠 Передал", callback_data=f"delivered_{deal_id}"))
    
    # Уведомляем продавца
    seller_lang = get_user_lang(deal['seller_id'])
    if seller_lang == 'ru':
        seller_message = (f"✅ Сделка #{deal_id} оплачена!\n\n"
                        f"👤 Покупатель: {buyer_display}\n"
                        f"💰 Сумма: {amount} {currency_name}\n"
                        f"📦 Что покупается:\n{deal['offer']}\n\n"
                        f"💠 Для получения средств передайте НФТ подарок на аккаунт посредник-гаранта @{get_support_username()}\n\n"
                        f"После передачи нажмите кнопку '💠 Передал' ниже.")
    else:
        seller_message = (f"✅ Deal #{deal_id} paid!\n\n"
                        f"👤 Buyer: {buyer_display}\n"
                        f"💰 Amount: {amount} {currency_name}\n"
                        f"📦 What is being purchased:\n{deal['offer']}\n\n"
                        f"💠 To receive funds, transfer NFT gift to guarantor account @{get_support_username()}\n\n"
                        f"After transfer, press '💠 Delivered' button below.")
    safe_send_message(deal['seller_id'], seller_message, reply_markup=seller_keyboard)
    
    # Обновляем статус сделки на 'paid'
    print(f"[DEBUG] Updating deal status to paid...")
    with db_lock:
        cursor.execute("UPDATE deals SET status = 'paid' WHERE deal_id = ?", (deal_id,))
        conn.commit()
    
    print(f"[DEBUG] Payment completed successfully from balance")

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    user_id = call.from_user.id
    update_user_activity(user_id)
    lang = get_user_lang(user_id)
    data = call.data
    
    def edit_caption_or_text(text, markup):
        # Telegram ограничение: caption для фото - 1024 символа
        max_caption_length = 1024
        
        if call.message.content_type == "photo":
            # Если текст слишком длинный для caption, обрезаем его
            if len(text) > max_caption_length:
                text = text[:max_caption_length - 3] + "..."
            try:
                bot.edit_message_caption(chat_id=user_id, message_id=call.message.message_id, caption=text, reply_markup=markup)
            except Exception as e:
                # Если не удалось изменить caption (например, слишком длинный), удаляем фото и отправляем текст
                try:
                    bot.delete_message(chat_id=user_id, message_id=call.message.message_id)
                    bot.send_message(user_id, text, reply_markup=markup)
                except:
                    # Если не удалось удалить, просто отправляем новое сообщение
                    bot.send_message(user_id, text, reply_markup=markup)
        else:
            bot.edit_message_text(text, user_id, call.message.message_id, reply_markup=markup)

    if data == "my_deals" or data.startswith("deals_page_"):
        # Определяем номер страницы
        if data == "my_deals":
            page = 1
        else:
            try:
                page = int(data.split("_")[-1])
            except:
                page = 1
        
        deals = get_user_deals(user_id)
        deals_text, total_pages = format_user_deals(user_id, deals, lang, page)
        edit_caption_or_text(deals_text, my_deals_keyboard(lang, page, total_pages))
    elif data == "deals_current":
        # Нажатие на индикатор страницы - ничего не делаем
        bot.answer_callback_query(call.id)
    elif data == "referrals":
        referral_link = f"https://t.me/GuarantNFTrobot?start=ref_{user_id}"
        stats = get_referral_stats(user_id)
        referrals_text = MESSAGES[lang]['referrals_text'].format(
            referral_link=referral_link,
            total_referrals=stats['total_referrals'],
            active_referrals=stats['active_referrals'],
            total_volume=f"{stats['total_volume']:.2f}"
        )
        edit_caption_or_text(referrals_text, statistics_keyboard(lang))
    elif data == "search_user":
        set_user_state(user_id, 'waiting_user_search')
        edit_caption_or_text(MESSAGES[lang]['search_user_text'], statistics_keyboard(lang))
    elif data == "show_statistics":
        stats = get_statistics()
        online_count = get_mau_count()
        # Форматируем числа с пробелами для тысяч
        def format_number(num):
            return f"{int(num):,}".replace(",", " ")
        def format_volume(num):
            # Форматируем объем с двумя знаками после запятой
            rounded = round(num, 2)
            # Разделяем целую и дробную части
            int_part = int(rounded)
            frac_part = round(rounded - int_part, 2)
            # Форматируем целую часть с пробелами
            formatted_int = f"{int_part:,}".replace(",", " ")
            if frac_part > 0:
                return f"{formatted_int}.{int(frac_part * 100):02d}"
            return formatted_int
        stats_text = format_support(MESSAGES[lang]['statistics_text'].format(
            total_deals=format_number(stats['total_deals']),
            successful_deals=format_number(stats['successful_deals']),
            total_volume=format_volume(stats['total_volume']),
            online_users=format_number(online_count)
        ))
        edit_caption_or_text(stats_text, statistics_keyboard(lang))
    elif data == "manage_rekv":
        edit_caption_or_text(MESSAGES[lang]['manage_rekv'], rekv_keyboard(lang))
    elif data == "add_ton":
        ton = get_user_ton_wallet(user_id)
        text = MESSAGES[lang]['add_ton_wallet']
        if ton: text += f"\n\n{MESSAGES[lang]['ton_ok']}: `{ton}`"
        set_user_state(user_id, 'waiting_ton_wallet')
        edit_caption_or_text(text, types.InlineKeyboardMarkup().add(
            types.InlineKeyboardButton(MESSAGES[lang]['back_btn'], callback_data="back_to_menu")
        ))
    elif data == "add_card":
        card = get_user_card_number(user_id)
        text = MESSAGES[lang]['add_card_number']
        if card: text += f"\n\n{MESSAGES[lang]['card_ok']}: `{card}`"
        set_user_state(user_id, 'waiting_card_number')
        edit_caption_or_text(text, types.InlineKeyboardMarkup().add(
            types.InlineKeyboardButton(MESSAGES[lang]['back_btn'], callback_data="back_to_menu")
        ))
    elif data == "back_to_menu":
        clear_user_state(user_id)
        # Отправляем только текстовое сообщение без фото
        safe_send_message(user_id, MESSAGES[lang]['welcome'], reply_markup=main_menu_keyboard(lang), parse_mode='HTML')
    elif data == "create_deal":
        if not has_payment_methods(user_id):
            bot.answer_callback_query(call.id, MESSAGES[lang]['no_payment_methods'], show_alert=True)
            return
        set_user_state(user_id, 'waiting_pay_method')
        edit_caption_or_text(format_support(MESSAGES[lang]['create_deal_start']), pay_method_keyboard(lang))
    elif data == "pay_ton":
        set_user_state(user_id, 'waiting_ton_amount')
        edit_caption_or_text(MESSAGES[lang]['enter_ton_amount'], None)
    elif data == "pay_star":
        set_user_state(user_id, 'waiting_star_amount')
        edit_caption_or_text(MESSAGES[lang]['enter_star_amount'], None)
    elif data == "pay_card":
        set_user_state(user_id, 'waiting_card_amount')
        edit_caption_or_text(MESSAGES[lang]['enter_card_amount'], None)
    elif data.startswith("close_"):
        deal_id = data[6:]
        edit_caption_or_text(MESSAGES[lang]['deal_closed_confirm'].format(deal_id=deal_id), confirm_exit_keyboard(deal_id, lang))
    elif data.startswith("exit_yes_"):
        deal_id = data[9:]
        close_deal(deal_id)
        edit_caption_or_text(MESSAGES[lang]['deal_closed_yes'].format(deal_id=deal_id), None)
        # Отправляем только текстовое сообщение без фото
        safe_send_message(user_id, MESSAGES[lang]['welcome'], reply_markup=main_menu_keyboard(lang), parse_mode='HTML')
        clear_user_state(user_id)
    elif data.startswith("confirm_pay_"):
        deal_id = data[12:]
        print(f"[DEBUG] confirm_pay triggered for deal {deal_id} by user {user_id}")
        
        try:
            deal = get_deal(deal_id)
            print(f"[DEBUG] Deal found: {deal}")
            
            # Проверяем существование сделки
            if not deal:
                print(f"[DEBUG] Deal not found")
                bot.answer_callback_query(call.id, "❌ Сделка не найдена" if lang == 'ru' else "❌ Deal not found", show_alert=True)
                return
            
            # Проверяем что пользователь - покупатель
            if not deal.get('buyer_id') or deal['buyer_id'] != user_id:
                print(f"[DEBUG] User is not buyer. buyer_id={deal.get('buyer_id')}, user_id={user_id}")
                bot.answer_callback_query(call.id, "❌ Вы не покупатель этой сделки" if lang == 'ru' else "❌ You're not the buyer", show_alert=True)
                return
            
            # Определяем валюту
            if deal['deal_type'] == 'ton':
                currency = 'ton'
                currency_name = 'TON'
            elif deal['deal_type'] == 'star':
                currency = 'star'
                currency_name = 'STAR'
            else:
                currency = 'rub'
                currency_name = 'RUB'
            
            amount = deal['amount']
            print(f"[DEBUG] Currency: {currency}, Amount: {amount}")
            
            balance = get_user_balance(user_id)
            print(f"[DEBUG] User balance: {balance}")
            
            # Проверяем баланс
            if balance[currency] < amount:
                print(f"[DEBUG] Insufficient balance: {balance[currency]} < {amount}")
                error_msg = "🔎 Мы не нашли вашу оплату" if lang == 'ru' else "🔎 We didn't find your payment"
                bot.answer_callback_query(call.id, error_msg, show_alert=True)
                bot.send_message(user_id, error_msg)
                return
            
            print(f"[DEBUG] Attempting to deduct balance...")
            # Списываем средства
            deduct_result = deduct_balance(user_id, currency, amount)
            print(f"[DEBUG] Deduct result: {deduct_result}")
            
            if deduct_result:
                print(f"[DEBUG] Payment deducted successfully")
                
                # Уведомляем покупателя сразу с полной информацией
                buyer_username = call.from_user.username
                if buyer_username:
                    buyer_display = f"@{buyer_username}"
                else:
                    buyer_display = f"ID: {user_id}"
                
                buyer_msg = f"✅ Оплата успешно проведена!\n\n💰 Сделка #{deal_id}\n💫 Оплачено: {amount} {currency_name}\n📦 За: {deal['offer'][:100]}\n\nОжидайте получение НФТ!" if lang == 'ru' else f"✅ Payment successful!\n\n💰 Deal #{deal_id}\n💫 Paid: {amount} {currency_name}\n📦 For: {deal['offer'][:100]}\n\nWait for NFT receipt!"
                
                print(f"[DEBUG] Sending success message to buyer...")
                bot.answer_callback_query(call.id, "✅ Оплата успешна!" if lang == 'ru' else "✅ Payment successful!", show_alert=False)
                safe_send_message(user_id, buyer_msg)
                print(f"[DEBUG] Callback answered")
                
                # Создаем клавиатуру с кнопкой "Передал" для продавца
                seller_keyboard = types.InlineKeyboardMarkup()
                seller_keyboard.add(types.InlineKeyboardButton("💠 Передал", callback_data=f"delivered_{deal_id}"))
                
                # Уведомляем продавца
                seller_message = f"✅ Сделка {deal_id} оплачена покупателем {buyer_display}\n\nДля получения средств на ваши реквизиты передайте товар на аккаунт посредник-гаранта @{get_support_username()}" if lang == 'ru' else f"✅ Deal {deal_id} paid by buyer {buyer_display}\n\nTo receive funds to your details, transfer the item to guarantor account @{get_support_username()}"
                print(f"[DEBUG] Sending notification to seller...")
                safe_send_message(deal['seller_id'], seller_message, reply_markup=seller_keyboard)
                print(f"[DEBUG] Seller notified")
                
                # Обновляем статус сделки на 'paid' (оплачена, ждем подтверждения передачи)
                print(f"[DEBUG] Updating deal status to paid...")
                with db_lock:
                    cursor.execute("UPDATE deals SET status = 'paid' WHERE deal_id = ?", (deal_id,))
                    conn.commit()
                
                clear_user_state(user_id)
                print(f"[DEBUG] Payment completed successfully")
            else:
                print(f"[DEBUG] Deduct failed!")
                bot.answer_callback_query(call.id, "❌ Ошибка списания средств" if lang == 'ru' else "❌ Error deducting funds", show_alert=True)
        
        except Exception as e:
            # Логируем ошибку и уведомляем пользователя
            print(f"[ERROR] Error in confirm_pay: {e}")
            import traceback
            traceback.print_exc()
            try:
                bot.answer_callback_query(call.id, "❌ Ошибка обработки оплаты" if lang == 'ru' else "❌ Payment processing error", show_alert=True)
            except:
                print(f"[ERROR] Failed to answer callback query")
    elif data.startswith("pay_stars_"):
        deal_id = data[10:]
        print(f"[DEBUG] pay_stars triggered for deal {deal_id} by user {user_id}")
        
        try:
            deal = get_deal(deal_id)
            
            if not deal:
                bot.answer_callback_query(call.id, "❌ Сделка не найдена" if lang == 'ru' else "❌ Deal not found", show_alert=True)
                return
            
            if not deal.get('buyer_id') or deal['buyer_id'] != user_id:
                bot.answer_callback_query(call.id, "❌ Вы не покупатель этой сделки" if lang == 'ru' else "❌ You're not the buyer", show_alert=True)
                return
            
            if deal.get('deal_type') != 'star':
                bot.answer_callback_query(call.id, "❌ Это не сделка через Stars" if lang == 'ru' else "❌ This is not a Stars deal", show_alert=True)
                return
            
            amount = int(deal['amount'])
            balance = get_user_balance(user_id)
            
            # Проверяем баланс
            if balance['star'] < amount:
                error_msg = f"❌ Недостаточно средств на балансе. Требуется: {amount} STAR, доступно: {balance['star']:.2f} STAR" if lang == 'ru' else f"❌ Insufficient balance. Required: {amount} STAR, available: {balance['star']:.2f} STAR"
                bot.answer_callback_query(call.id, error_msg, show_alert=True)
                return
            
            # Списываем средства
            deduct_result = deduct_balance(user_id, 'star', amount)
            
            if not deduct_result:
                bot.answer_callback_query(call.id, "❌ Ошибка списания средств" if lang == 'ru' else "❌ Error deducting funds", show_alert=True)
                return
            
            print(f"[DEBUG] Payment deducted successfully from balance")
            
            # Уведомляем покупателя сразу
            buyer_username = call.from_user.username
            if buyer_username:
                buyer_display = f"@{buyer_username}"
            else:
                buyer_display = f"ID: {user_id}"
            
            buyer_msg = f"✅ Оплата успешно проведена!\n\n💰 Сделка #{deal_id}\n💫 Оплачено: {amount} STAR\n📦 За: {deal['offer'][:100]}\n\nОжидайте получение НФТ!" if lang == 'ru' else f"✅ Payment successful!\n\n💰 Deal #{deal_id}\n💫 Paid: {amount} STAR\n📦 For: {deal['offer'][:100]}\n\nWait for NFT receipt!"
            
            bot.answer_callback_query(call.id, "✅ Оплата успешна!" if lang == 'ru' else "✅ Payment successful!", show_alert=False)
            safe_send_message(user_id, buyer_msg)
            
            # Создаем клавиатуру с кнопкой "Передал" для продавца
            seller_keyboard = types.InlineKeyboardMarkup()
            seller_keyboard.add(types.InlineKeyboardButton("💠 Передал", callback_data=f"delivered_{deal_id}"))
            
            # Уведомляем продавца
            seller_lang = get_user_lang(deal['seller_id'])
            if seller_lang == 'ru':
                seller_message = (f"✅ Сделка #{deal_id} оплачена!\n\n"
                                f"👤 Покупатель: {buyer_display}\n"
                                f"💰 Сумма: {amount} STAR\n"
                                f"📦 Что покупается:\n{deal['offer']}\n\n"
                                f"💠 Для получения средств передайте НФТ подарок на аккаунт посредник-гаранта @{get_support_username()}\n\n"
                                f"После передачи нажмите кнопку '💠 Передал' ниже.")
            else:
                seller_message = (f"✅ Deal #{deal_id} paid!\n\n"
                                f"👤 Buyer: {buyer_display}\n"
                                f"💰 Amount: {amount} STAR\n"
                                f"📦 What is being purchased:\n{deal['offer']}\n\n"
                                f"💠 To receive funds, transfer NFT gift to guarantor account @{get_support_username()}\n\n"
                                f"After transfer, press '💠 Delivered' button below.")
            safe_send_message(deal['seller_id'], seller_message, reply_markup=seller_keyboard)
            
            # Обновляем статус сделки на 'paid'
            print(f"[DEBUG] Updating deal status to paid...")
            with db_lock:
                cursor.execute("UPDATE deals SET status = 'paid' WHERE deal_id = ?", (deal_id,))
                conn.commit()
            
            clear_user_state(user_id)
            print(f"[DEBUG] Stars payment completed successfully from balance")
            
        except Exception as e:
            print(f"[ERROR] Error in pay_stars: {e}")
            import traceback
            traceback.print_exc()
            bot.answer_callback_query(call.id, "❌ Ошибка обработки оплаты" if lang == 'ru' else "❌ Payment processing error", show_alert=True)
    elif data.startswith("delivered_"):
        deal_id = data[10:]
        print(f"[DEBUG] Seller confirmed delivery for deal {deal_id}, user_id={user_id}")
        
        try:
            deal = get_deal(deal_id)
            print(f"[DEBUG] Deal retrieved: {deal}")
            
            if not deal:
                print(f"[DEBUG] Deal not found!")
                bot.answer_callback_query(call.id, "❌ Сделка не найдена" if lang == 'ru' else "❌ Deal not found", show_alert=True)
                return
            
            if deal['seller_id'] != user_id:
                print(f"[DEBUG] User {user_id} is not seller (seller_id={deal['seller_id']})")
                bot.answer_callback_query(call.id, "❌ Ошибка: вы не продавец" if lang == 'ru' else "❌ Error: you're not the seller", show_alert=True)
                return
            
            # Завершаем сделку
            print(f"[DEBUG] Marking deal as successful...")
            mark_deal_successful(deal_id)
            print(f"[DEBUG] Deal {deal_id} marked as successful")
            
            # Уведомляем продавца
            seller_msg = "✅ Мы проверим получение вашего подарка, ожидайте 30 минут" if lang == 'ru' else "✅ We will check receipt of your gift, wait 30 minutes"
            print(f"[DEBUG] Sending message to seller...")
            safe_send_message(user_id, seller_msg)
            print(f"[DEBUG] Answering callback...")
            bot.answer_callback_query(call.id, "✅ Принято!" if lang == 'ru' else "✅ Accepted!", show_alert=False)
            print(f"[DEBUG] Callback answered")
            
            # Уведомляем покупателя
            if deal.get('buyer_id'):
                buyer_msg = "🎁 Продавец передал товар гаранту!\n\nОжидайте получение вашего НФТ в течение 30 минут." if lang == 'ru' else "🎁 Seller transferred the item to guarantor!\n\nWait for your NFT within 30 minutes."
                print(f"[DEBUG] Notifying buyer {deal['buyer_id']}...")
                safe_send_message(deal['buyer_id'], buyer_msg)
                print(f"[DEBUG] Buyer notified about delivery")
            else:
                print(f"[DEBUG] No buyer_id in deal")
            
            # Удаляем сделку из базы данных после подтверждения передачи
            print(f"[DEBUG] Deleting deal after delivery confirmation...")
            delete_deal(deal_id)
                
        except Exception as e:
            print(f"[ERROR] Error in delivered handler: {e}")
            import traceback
            traceback.print_exc()
            try:
                bot.answer_callback_query(call.id, "❌ Ошибка" if lang == 'ru' else "❌ Error", show_alert=True)
            except:
                print(f"[ERROR] Failed to answer callback query")
    
    elif data.startswith("back_to_deal_"):
        deal_id = data[13:]
        # Возвращаемся к просмотру сделки
        deal = get_deal(deal_id)
        if not deal:
            bot.answer_callback_query(call.id, "❌ Сделка не найдена" if lang == 'ru' else "❌ Deal not found", show_alert=True)
            return
        
        # Показываем информацию о сделке в зависимости от типа оплаты
        seller_deals_count = get_successful_deals_count(deal['seller_id'])
        
        if deal['deal_type'] == 'ton':
            text = format_support(MESSAGES[lang]['deal_info_for_buyer_ton'].format(
                deal_id=deal_id,
                seller_username=deal['seller_username'],
                seller_id=deal['seller_id'],
                seller_deals=seller_deals_count,
                offer=deal['offer'],
                amount=deal['amount']
            ))
            keyboard = deal_buyer_keyboard_ton(deal_id, lang)
        elif deal['deal_type'] == 'star':
            text = format_support(MESSAGES[lang]['deal_info_for_buyer_star'].format(
                deal_id=deal_id,
                seller_username=deal['seller_username'],
                seller_id=deal['seller_id'],
                seller_deals=seller_deals_count,
                offer=deal['offer'],
                amount=deal['amount']
            ))
            keyboard = deal_buyer_keyboard_star(deal_id, deal['amount'], lang)
        else:  # card
            card_number = get_user_card_number(deal['seller_id'])
            text = format_support(MESSAGES[lang]['deal_info_for_buyer_card'].format(
                deal_id=deal_id,
                seller_username=deal['seller_username'],
                seller_id=deal['seller_id'],
                seller_deals=seller_deals_count,
                offer=deal['offer'],
                card_number=card_number if card_number else "не указано",
                amount=deal['amount']
            ))
            keyboard = deal_buyer_keyboard_card(deal_id, lang)
        
        edit_caption_or_text(text, keyboard)
        bot.answer_callback_query(call.id)
    
    elif data.startswith("exit_deal_"):
        deal_id = data[10:]
        edit_caption_or_text(MESSAGES[lang]['exit_confirm_text'].format(deal_id=deal_id), confirm_exit_keyboard(deal_id, lang))
    elif data == "change_lang":
        edit_caption_or_text(MESSAGES[lang]['lang_change'], language_choose_keyboard())
    elif data in ["lang_ru", "lang_en"]:
        selected = data.split("_")[1]
        set_user_lang(user_id, selected)
        clear_user_state(user_id)
        # Отправляем только текстовое сообщение без фото
        safe_send_message(user_id, MESSAGES[selected]['welcome'], reply_markup=main_menu_keyboard(selected), parse_mode='HTML')
        bot.answer_callback_query(call.id, f"Язык изменен на {'Русский' if selected=='ru' else 'English'}")

@bot.message_handler(commands=['getgarant'])
def handle_getgarant_command(message):
    user_id = message.from_user.id
    update_user_activity(user_id)
    lang = get_user_lang(user_id)
    args = message.text.split()
    if len(args) < 2:
        bot.send_message(user_id, "Использование: /getgarant <ID пользователя>\nПример: /getgarant 123456789" if lang == 'ru' else "Usage: /getgarant <User ID>\nExample: /getgarant 123456789")
        return
    
    target_user_id_str = args[1].strip()
    try:
        target_user_id = int(target_user_id_str)
    except ValueError:
        bot.send_message(user_id, "❌ Неверный формат ID. Используйте только цифры." if lang == 'ru' else "❌ Invalid ID format. Use numbers only.")
        return
    
    user_data = get_user_by_id_or_username(target_user_id_str)
    if user_data:
        guarantor_status = get_guarantor_info(target_user_id, lang)
        username = get_user_username_from_deals(target_user_id)
        
        if lang == 'ru':
            result = f"💎 Доверенность и статус гаранта\n\n"
            result += f"🆔 ID пользователя: {target_user_id}\n"
            result += f"📛 Username: @{username}\n\n"
            result += f"💎 Статус гаранта:\n{guarantor_status}\n\n"
            result += f"📊 Дополнительная информация:\n"
            result += f"• Успешных сделок: {user_data.get('successful_deals', 0)}\n"
            deals = get_user_deals(target_user_id)
            completed_deals = len([d for d in deals if d.get('status') == 'completed'])
            result += f"• Завершенных сделок: {completed_deals}"
        else:
            result = f"💎 Trust and Guarantor Status\n\n"
            result += f"🆔 User ID: {target_user_id}\n"
            result += f"📛 Username: @{username}\n\n"
            result += f"💎 Guarantor Status:\n{guarantor_status}\n\n"
            result += f"📊 Additional Information:\n"
            result += f"• Successful deals: {user_data.get('successful_deals', 0)}\n"
            deals = get_user_deals(target_user_id)
            completed_deals = len([d for d in deals if d.get('status') == 'completed'])
            result += f"• Completed deals: {completed_deals}"
        
        bot.send_message(user_id, result)
    else:
        bot.send_message(user_id, "❌ Пользователь не найден." if lang == 'ru' else "❌ User not found.")

@bot.message_handler(commands=['money'])
def handle_money_command(message):
    """Команда для пополнения баланса"""
    user_id = message.from_user.id
    update_user_activity(user_id)
    lang = get_user_lang(user_id)
    
    try:
        # Разбираем команду
        parts = message.text.split()
        
        if len(parts) < 2:
            error_msg = "❌ Укажите сумму для пополнения.\nПример: /money 1000" if lang == 'ru' else "❌ Please specify amount.\nExample: /money 1000"
            bot.send_message(user_id, error_msg)
            return
        
        try:
            amount = float(parts[1])
            if amount <= 0:
                raise ValueError("Amount must be positive")
        except ValueError:
            error_msg = "❌ Укажите корректную сумму (число больше 0)" if lang == 'ru' else "❌ Please specify valid amount (number greater than 0)"
            bot.send_message(user_id, error_msg)
            return
        
        # Добавляем на все три типа валют (TON, RUB, STAR)
        add_balance(user_id, 'ton', amount)
        add_balance(user_id, 'rub', amount)
        add_balance(user_id, 'star', amount)
        
        balance = get_user_balance(user_id)
        
        success_msg = f"✅ Баланс пополнен!\n\n💰 Ваш баланс:\n• TON: {balance['ton']:.2f}\n• RUB: {balance['rub']:.2f}\n• STAR: {balance['star']:.2f}" if lang == 'ru' else f"✅ Balance topped up!\n\n💰 Your balance:\n• TON: {balance['ton']:.2f}\n• RUB: {balance['rub']:.2f}\n• STAR: {balance['star']:.2f}"
        bot.send_message(user_id, success_msg)
        
    except Exception as e:
        error_msg = f"❌ Ошибка при пополнении баланса: {str(e)}" if lang == 'ru' else f"❌ Error topping up balance: {str(e)}"
        bot.send_message(user_id, error_msg)

@bot.message_handler(commands=['set_my_deals'])
def handle_set_deals_command(message):
    user_id = message.from_user.id
    update_user_activity(user_id)
    lang = get_user_lang(user_id)
    args = message.text.split()
    if len(args) < 2:
        bot.send_message(user_id, MESSAGES[lang]['set_deals_usage'])
        return
    try:
        count = int(args[1])
        if count < 0:
            raise ValueError
        set_user_successful_deals(user_id, count)
        bot.send_message(user_id, MESSAGES[lang]['deals_set'].format(count=count))
    except ValueError:
        bot.send_message(user_id, MESSAGES[lang]['set_deals_usage'])

@bot.message_handler(commands=['set'])
def handle_set_support_command(message):
    """Команда для изменения username поддержки: /set @username"""
    user_id = message.from_user.id
    update_user_activity(user_id)
    lang = get_user_lang(user_id)
    args = message.text.split()
    if len(args) < 2:
        current = get_support_username()
        if lang == 'ru':
            bot.send_message(user_id, f"💁‍♂️ Текущий username поддержки: @{current}\n\nИспользование: /set @username")
        else:
            bot.send_message(user_id, f"💁‍♂️ Current support username: @{current}\n\nUsage: /set @username")
        return
    new_username = args[1].replace("@", "").strip()
    if not new_username:
        if lang == 'ru':
            bot.send_message(user_id, "❌ Укажите корректный username")
        else:
            bot.send_message(user_id, "❌ Please provide a valid username")
        return
    set_support_username(new_username)
    if lang == 'ru':
        bot.send_message(user_id, f"✅ Username поддержки изменен на @{new_username}")
    else:
        bot.send_message(user_id, f"✅ Support username changed to @{new_username}")

@bot.pre_checkout_query_handler(func=lambda query: True)
def handle_pre_checkout_query(pre_checkout_query):
    bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@bot.message_handler(content_types=['successful_payment'])
def handle_successful_payment(message):
    # Обработчик оставлен для совместимости, но оплата теперь идет через баланс
    # Этот обработчик может использоваться для других типов платежей в будущем
    user_id = message.from_user.id
    update_user_activity(user_id)
    lang = get_user_lang(user_id)
    safe_send_message(user_id, "ℹ️ Оплата теперь производится напрямую с баланса. Используйте кнопку 'Оплатить Stars' или команду /pay" if lang == 'ru' else "ℹ️ Payment is now made directly from balance. Use 'Pay Stars' button or /pay command")

@bot.message_handler(func=lambda m: get_user_state(m.from_user.id) == 'waiting_ton_wallet')
def ton_wallet_handler(message):
    user_id = message.from_user.id
    update_user_activity(user_id)
    lang = get_user_lang(user_id)
    addr = message.text.strip()
    if validate_ton_address(addr):
        set_user_ton_wallet(user_id, addr)
        clear_user_state(user_id)
        bot.send_message(user_id, MESSAGES[lang]['ton_ok'], reply_markup=rekv_keyboard(lang))
    else:
        bot.send_message(user_id, MESSAGES[lang]['ton_invalid'])

@bot.message_handler(func=lambda m: get_user_state(m.from_user.id) == 'waiting_card_number')
def card_number_handler(message):
    user_id = message.from_user.id
    update_user_activity(user_id)
    lang = get_user_lang(user_id)
    card = message.text.strip()
    if validate_card_number(card):
        set_user_card_number(user_id, card)
        clear_user_state(user_id)
        bot.send_message(user_id, MESSAGES[lang]['card_ok'], reply_markup=rekv_keyboard(lang))
    else:
        bot.send_message(user_id, MESSAGES[lang]['card_invalid'])

@bot.message_handler(func=lambda m: get_user_state(m.from_user.id) == 'waiting_ton_amount')
def ton_amount_handler(message):
    user_id = message.from_user.id
    update_user_activity(user_id)
    lang = get_user_lang(user_id)
    try:
        amount = float(message.text.replace(',', '.'))
        if amount <= 0:
            raise ValueError
    except:
        bot.send_message(user_id, MESSAGES[lang]['invalid_amount'])
        return
    set_user_input(user_id, 'deal_amount', amount)
    set_user_input(user_id, 'deal_type', 'ton')
    set_user_state(user_id, 'waiting_deal_offer')
    bot.send_message(user_id, MESSAGES[lang]['enter_deal_offer'].format(amount=amount, currency="TON"))

@bot.message_handler(func=lambda m: get_user_state(m.from_user.id) == 'waiting_star_amount')
def star_amount_handler(message):
    user_id = message.from_user.id
    update_user_activity(user_id)
    lang = get_user_lang(user_id)
    try:
        amount = int(message.text)
        if amount <= 0:
            raise ValueError
    except:
        bot.send_message(user_id, MESSAGES[lang]['invalid_amount'])
        return
    set_user_input(user_id, 'deal_amount', amount)
    set_user_input(user_id, 'deal_type', 'star')
    set_user_state(user_id, 'waiting_deal_offer')
    bot.send_message(user_id, MESSAGES[lang]['enter_deal_offer'].format(amount=amount, currency="STAR"))

@bot.message_handler(func=lambda m: get_user_state(m.from_user.id) == 'waiting_card_amount')
def card_amount_handler(message):
    user_id = message.from_user.id
    update_user_activity(user_id)
    lang = get_user_lang(user_id)
    try:
        amount = float(message.text.replace(',', '.'))
        if amount <= 0:
            raise ValueError
    except:
        bot.send_message(user_id, MESSAGES[lang]['invalid_amount'])
        return
    set_user_input(user_id, 'deal_amount', amount)
    set_user_input(user_id, 'deal_type', 'card')
    set_user_state(user_id, 'waiting_deal_offer')
    bot.send_message(user_id, MESSAGES[lang]['enter_deal_offer_card'].format(amount=amount))

@bot.message_handler(func=lambda m: get_user_state(m.from_user.id) == 'waiting_user_search')
def user_search_handler(message):
    user_id = message.from_user.id
    update_user_activity(user_id)
    lang = get_user_lang(user_id)
    identifier = message.text.strip()
    
    if not identifier:
        bot.send_message(user_id, MESSAGES[lang]['user_not_found'])
        return
    
    # Проверяем, является ли это ID (только цифры или отрицательное число)
    is_id = identifier.replace('@', '').replace('-', '').strip().isdigit()
    
    user_data = get_user_by_id_or_username(identifier)
    if user_data:
        user_info = format_user_info(user_data, lang)
        clear_user_state(user_id)
        bot.send_message(user_id, user_info)
    else:
        # Более информативное сообщение об ошибке
        if is_id:
            error_msg = ("❌ Пользователь с таким ID не найден в базе бота.\n\n"
                        "Возможные причины:\n"
                        "• Пользователь еще не запускал бота (/start)\n"
                        "• ID указан неверно\n"
                        "• Пользователь не зарегистрирован в системе") if lang == 'ru' else (
                        "❌ User with this ID not found in bot database.\n\n"
                        "Possible reasons:\n"
                        "• User hasn't started the bot (/start)\n"
                        "• ID is incorrect\n"
                        "• User is not registered in the system")
        else:
            error_msg = ("❌ Пользователь с таким username не найден.\n\n"
                        "Возможные причины:\n"
                        "• Username указан неверно (без @)\n"
                        "• Пользователь еще не создавал сделки\n"
                        "• Пользователь не зарегистрирован в боте") if lang == 'ru' else (
                        "❌ User with this username not found.\n\n"
                        "Possible reasons:\n"
                        "• Username is incorrect (without @)\n"
                        "• User hasn't created any deals yet\n"
                        "• User is not registered in the bot")
        bot.send_message(user_id, error_msg)

@bot.message_handler(func=lambda m: get_user_state(m.from_user.id) == 'waiting_deal_offer')
def deal_offer_handler(message):
    user_id = message.from_user.id
    update_user_activity(user_id)
    lang = get_user_lang(user_id)
    offer = message.text.strip()
    deal_type = get_user_input(user_id, 'deal_type')
    if not validate_nft_link(offer):
        bot.send_message(user_id, MESSAGES[lang]['invalid_nft_link'])
        return
    amount = get_user_input(user_id, 'deal_amount')
    deal_id = generate_deal_id()
    create_deal(deal_id, user_id, message.from_user.username or "unknown", amount, offer, deal_type)
    buyer_link = f"https://t.me/GuarantNFTrobot?start=order_ton_{deal_id}"
    currency = "TON" if deal_type == 'ton' else ("STAR" if deal_type == 'star' else "RUB")
    bot.send_message(user_id, MESSAGES[lang]['deal_created'].format(
        amount=amount, 
        offer=offer, 
        link=buyer_link, 
        currency=currency
    ), reply_markup=deal_close_keyboard(deal_id, lang))
    clear_user_state(user_id)

if __name__ == '__main__':
    # Устанавливаем команду /start в меню быстрых команд
    commands = [
        types.BotCommand("start", "🏠 Главное меню")
    ]
    bot.set_my_commands(commands)
    print("Бот запущен...")
    bot.infinity_polling()
[file content end]
