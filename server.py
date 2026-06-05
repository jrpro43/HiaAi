from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import json
import time
import sqlite3
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import threading
from queue import Queue
import re

app = Flask(__name__)
CORS(app)

# ==================== ډیټابیس ====================
class Database:
    def __init__(self):
        self.conn = sqlite3.connect('hia_knowledge.db', check_same_thread=False)
        self.init_db()
    
    def init_db(self):
        cursor = self.conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS crawled_pages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT,
                title TEXT,
                content TEXT,
                keywords TEXT,
                images TEXT,
                crawled_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS chat_knowledge (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                query TEXT,
                response TEXT,
                source TEXT,
                created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        self.conn.commit()
    
    def save_page(self, url, title, content, keywords, images):
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO crawled_pages (url, title, content, keywords, images)
            VALUES (?, ?, ?, ?, ?)
        ''', (url, title, content[:5000], json.dumps(keywords), json.dumps(images)))
        self.conn.commit()
    
    def search_knowledge(self, query):
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT response FROM chat_knowledge 
            WHERE query LIKE ? 
            ORDER BY created_date DESC LIMIT 1
        ''', (f'%{query}%',))
        result = cursor.fetchone()
        return result[0] if result else None
    
    def save_knowledge(self, query, response, source):
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO chat_knowledge (query, response, source)
            VALUES (?, ?, ?)
        ''', (query, response, source))
        self.conn.commit()

db = Database()
crawl_queue = Queue()
is_crawling = False

# ==================== ویب کراولر ====================
class WebCrawler:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    def crawl(self, url):
        try:
            response = self.session.get(url, timeout=10)
            soup = BeautifulSoup(response.content, 'html.parser')
            
            title = soup.title.string if soup.title else url
            text = soup.get_text()[:5000]
            
            # د کلیمو استخراج
            keywords = re.findall(r'\b\w{4,}\b', text)[:10]
            
            # د انځورونو استخراج
            images = []
            for img in soup.find_all('img')[:5]:
                src = img.get('src', '')
                if src:
                    images.append(src)
            
            return {
                'url': url,
                'title': title,
                'content': text,
                'keywords': keywords,
                'images': images
            }
        except Exception as e:
            return None

crawler = WebCrawler()

# ==================== API Routes ====================
@app.route('/api/start-crawl', methods=['POST'])
def start_crawl():
    global is_crawling
    data = request.json
    urls = data.get('urls', [])
    
    if is_crawling:
        return jsonify({'message': 'کراول کول دمخه روان دی'})
    
    is_crawling = True
    
    def crawl_worker():
        global is_crawling
        for url in urls:
            if not is_crawling:
                break
            result = crawler.crawl(url)
            if result:
                db.save_page(
                    result['url'],
                    result['title'],
                    result['content'],
                    result['keywords'],
                    result['images']
                )
            time.sleep(0.1)
        is_crawling = False
    
    thread = threading.Thread(target=crawl_worker)
    thread.start()
    
    return jsonify({'message': f'د {len(urls)} سایټونو کراول کول پیل شو'})

@app.route('/api/stop-crawl', methods=['POST'])
def stop_crawl():
    global is_crawling
    is_crawling = False
    return jsonify({'message': 'کراول کول ودرول شو'})

@app.route('/api/chat', methods=['POST'])
def chat():
    data = request.json
    query = data.get('message', '')
    
    # لومړی په محلي ډیټابیس کې لټون
    local_response = db.search_knowledge(query)
    
    if local_response:
        return jsonify({
            'response': local_response,
            'source': 'local_database'
        })
    
    # که ځواب ونه موندل شو، ګوګل سرچ
    try:
        # دلته د ګوګل API یا د DuckDuckGo څخه استفاده کولی شئ
        search_response = f'د "{query}" په اړه معلومات مې راټول کړل. دا یوه مهمه موضوع ده.'
        
        # ذخیره کول
        db.save_knowledge(query, search_response, 'google_search')
        
        return jsonify({
            'response': search_response,
            'source': 'google_search'
        })
    except Exception as e:
        return jsonify({
            'response': 'بخښنه غواړم، د معلوماتو په ترلاسه کولو کې ستونزه رامنځته شوه.',
            'source': 'error'
        })

@app.route('/api/knowledge', methods=['GET'])
def get_knowledge():
    # د ذخیره شویو معلوماتو لیست
    return jsonify({
        'total_pages': 0,
        'knowledge_items': []
    })

if __name__ == '__main__':
    print('🚀 HIA AI Server Starting...')
    print('📡 Web Crawler: Ready')
    print('🤖 AI Chatbot: Ready')
    print('🌐 Server: http://localhost:5000')
    app.run(debug=True, port=5000, threaded=True) 
