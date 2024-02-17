from argparse import Namespace
from pathlib import Path
import sqlite3
from typing import Optional


class Vocabdb:
    def __init__(self, db: Path) -> None:
        self.__db_path = db
        self.__db: Optional[sqlite3.Connection] = None
       
    def open(self):
        if self.is_open():
            raise ValueError('Database already open')
        
        self.__db = sqlite3.connect(str(self.__db_path))

    def close(self):
        if self.is_open():
            self.__db.close()
            self.__db = None

    def is_open(self):
        return self.__db is not None

    def get_books(self):
        self.__check_db_open()
        
        cursor = self.__db.cursor()
        cursor.execute(f'select * from BOOK_INFO')
        
        books = {}
        for row in cursor.fetchall():
            books[row[0]] = Namespace(**{
                'id': row[0],
                'asin': row[1],
                'guid': row[2],
                'lang': row[3],
                'title': row[4],
                'authors': row[5]
            })
        
        cursor.close()

        return books
        
    def get_lookups(self, book_id: Optional[str] = None):
        self.__check_db_open()
        
        cursor = self.__db.cursor() # type: ignore

        query = 'select * from LOOKUPS l'

        if book_id is not None:
            query += f" where l.book_key = ?"
            cursor.execute(query, (book_id,))
        else:
            cursor.execute(query)
        
        lookups = {}
        for row in cursor.fetchall():
            lookups[row[0]] = Namespace(**{
                'id': row[0],
                'word_id': row[1],
                'book_id': row[2],
                'dict_id': row[3],
                'pos': row[4],
                'usage': row[5],
                'timestamp': row[6],
            })
        
        cursor.close()

        return lookups

    def get_words(self, book_id: Optional[str] = None):
        self.__check_db_open()
        
        cursor = self.__db.cursor() # type: ignore
        if book_id is None:
            cursor.execute(f'select * from WORDS')
        else:
            cursor.execute(f"select w.id, w.word, w.stem, w.lang, w.category, w.timestamp, w.profileid from LOOKUPS l join WORDS w on l.word_key = w.id where l.book_key = ?", (book_id,))

        words = {}
        for row in cursor.fetchall():
            words[row[0]] = Namespace(**{
                'id': row[0],
                'value': row[1],
                'stem': row[2],
                'lang': row[3],
                'category': row[4],
                'timestamp': row[5],
                'profileid': row[6]
            })
        
        cursor.close()

        return words


    def __check_db_open(self):
        if not self.is_open():
            raise ValueError('Open the database before using it')

    def __enter__(self):
        self.open()
        return self
    
    def __exit__(self, exception_type, exception_value, exception_traceback):
        self.close()
