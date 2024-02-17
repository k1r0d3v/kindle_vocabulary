from abc import ABC, abstractmethod
from pathlib import Path
import sqlite3
from typing import Optional, Self
from vocabdb import Vocabdb


class VocabularyEntry:
    def __init__(self) -> None:
        self.lang: Optional[str] = None
        self.word: Optional[str] = None
        self.usage_word_index: Optional[int] = None
        self.usage: Optional[str] = None
        self.translator: Optional[str] = None
        self.translation: Optional[str] = None

    def copy(self):
        entry = VocabularyEntry()
        entry.lang = self.lang
        entry.word = self.word
        entry.usage_word_index = self.usage_word_index
        entry.usage = self.usage
        entry.translator = self.translator
        entry.translation = self.translation
        return entry


class VocabularyIndex:
    def __init__(self, db_path = Path('./vindex.db'), from_lang = 'en', to_lang = 'es', auto_commit = True) -> None:
        super().__init__()
        self.__db_path = db_path
        self._from_lang = from_lang
        self._to_lang = to_lang
        self.__auto_commit = auto_commit
        self.__db: Optional[sqlite3.Connection] = None
       
    def open(self) -> None:
        if self.is_open():
            raise ValueError('Database already open')
        
        if self.__db_path.exists():
            self.__db = sqlite3.connect(str(self.__db_path))
        else:
            self.__db = sqlite3.connect(str(self.__db_path))
            cursor = self.__db.cursor()
            cursor.execute(f'create table {self.__db_table()}(word TEXT PRIMARY KEY, usage_word_index INTEGER, usage TEXT, translator TEXT, translation TEXT)')
            cursor.close()

    def close(self) -> None:
        if self.is_open():
            self.__db.commit() # type: ignore
            self.__db.close() # type: ignore
            self.__db = None

    def commit(self) -> None:
        if self.is_open():
            self.__db.commit() # type: ignore

    def is_open(self):
        return self.__db is not None

    def __db_table(self) -> str:
        return f'{self._from_lang}_{self._to_lang}'

    def __check_db_open(self) -> None:
        if self.__db is None:
            raise ValueError('Open the database before using it')

    def __enter__(self):
        self.open()
        return self
    
    def __exit__(self, exception_type, exception_value, exception_traceback):
        self.close()

    def read_entries(self) -> list[VocabularyEntry]:
        self.__check_db_open()

        cursor = self.__db.cursor() # type: ignore
        cursor.execute(f'select * from {self.__db_table()}')

        entries = []
        for row in cursor.fetchall():                
            entry = VocabularyEntry()
            entry.lang = self._from_lang
            entry.word = row[0]
            entry.usage_word_index = row[1]
            entry.usage = row[2]
            entry.translator = row[3]
            entry.translation = row[4]

            entries.append(entry)

        cursor.close()

        return entries

    def read_entry(self, word) -> Optional[VocabularyEntry]:
        self.__check_db_open()

        cursor = self.__db.cursor() # type: ignore
        cursor.execute(f"select * from {self.__db_table()} where word = ?", (word,))

        row = cursor.fetchone()
        if row is None:
            return None
        
        entry = VocabularyEntry()
        entry.lang = self._from_lang
        entry.word = row[0]
        entry.usage_word_index = row[1]
        entry.usage = row[2]
        entry.translator = row[3]
        entry.translation = row[4]

        cursor.close()

        return entry

    def write_entry(self, entry: VocabularyEntry) -> None:
        self.__check_db_open()

        cursor = self.__db.cursor() # type: ignore   
        cursor.execute(f"insert or replace into {self.__db_table()} values(?, ?, ?, ?, ?)", (entry.word, entry.usage_word_index, entry.usage, entry.translator, entry.translation))
        cursor.close()

        if self.__auto_commit:
            self.__db.commit() # type: ignore


class VocabularyEntryTransform(ABC):
    @abstractmethod
    def transform(self, builder, entry: VocabularyEntry) -> list[VocabularyEntry]:
        pass


class VocabularyEntryTranslator(ABC):
    @abstractmethod
    def key(self) -> str:
        pass
                  
    @abstractmethod
    def translate(self, entry: VocabularyEntry) -> Optional[str]:
        pass

    @abstractmethod
    def should_update(self, newEntry: VocabularyEntry, oldEntry: VocabularyEntry) -> bool:
        pass


class VocabularyIndexBuilder(ABC):
    def __init__(self) -> None:
        self._from_lang: Optional[str] = None
        self._to_lang: Optional[str] = None
        self._transforms: list[VocabularyEntryTransform] = []
        self._translator: Optional[VocabularyEntryTranslator] = None

    def add_transform(self, transform: VocabularyEntryTransform) -> Self:
        self._transforms.append(transform)
        return self
    
    def set_transforms(self, transforms: list[VocabularyEntryTransform]) -> Self:
        self._transforms = transforms
        return self

    def set_to_lang(self, to_lang: Optional[str]) -> Self:
        self._to_lang = to_lang
        return self
    
    def set_from_lang(self, from_lang: Optional[str]) -> Self:
        self._from_lang = from_lang
        return self
    
    def set_translator(self, translator: Optional[VocabularyEntryTranslator]) -> Self:
        self._translator = translator
        return self

    @abstractmethod
    def build(self) -> VocabularyIndex:
        pass


class VocabularyIndexBuilderFromDict(VocabularyIndexBuilder):
    def __init__(self, vocabulary: dict, db_path = Path('vindex.db')) -> None:
        super().__init__()
        self.__vocabulary = vocabulary
        self.__db_path = db_path

    def build(self) -> VocabularyIndex:
        if self._from_lang is None:
            raise ValueError('"From" language is not set')
        
        if self._to_lang is None:
            raise ValueError('"To" language is not set')

        with VocabularyIndex(db_path=self.__db_path, 
                             from_lang=self._from_lang, 
                             to_lang=self._to_lang) as index:
            
            entries: dict[str, VocabularyEntry] = {}
            for word, value in self.__vocabulary.items():
                for new_entry in self.__process_entry(word, value):
                    new_word = new_entry.word

                    if new_word is None:
                        raise ValueError('Unexpected word value: None')

                    if new_word in entries:
                        continue

                    entries[new_word] = new_entry

            # Index building
            total_words = len(entries)
            current_word_count = 1
            for entry in entries.values():
                existing_entry = index.read_entry(entry.word)

                if self._translator is None:
                    if existing_entry is None:
                        print(f'[VocabularyIndexBuilderFromDict] Indexing {current_word_count}/{total_words}: {entry.word}')
                        index.write_entry(entry)
                    else:
                        print(f'[VocabularyIndexBuilderFromDict] Skipping {current_word_count}/{total_words}, reusing index: "{entry.word}"')
                else:
                    if existing_entry is None or self._translator.should_update(entry, existing_entry):
                        entry.translator = self._translator.key()
                        entry.translation = self._translator.translate(entry)

                        print(f'[VocabularyIndexBuilderFromDict] Indexing {current_word_count}/{total_words}: {entry.word}')
                        index.write_entry(entry)
                    else:
                        print(f'[VocabularyIndexBuilderFromDict] Skipping {current_word_count}/{total_words}, reusing index: "{entry.word}"')
                
                current_word_count += 1
            return index

    def __process_entry(self, word, value) -> list[VocabularyEntry]:
        if 'usage' not in value.keys():
            raise ValueError(f'Expected an usage key for word: {word}')
        
        if 'usage_word_index' not in value.keys():
            raise ValueError(f'Expected an usage word index key for word: {word}')

        entry = VocabularyEntry()
        entry.lang = self._from_lang
        entry.word = word.strip()
        entry.usage = value.get('usage')
        entry.usage_word_index = value.get('usage_word_index')

        if len(self._transforms) == 0:
            return [entry]

        entries = []    
        for transform in self._transforms:
            for transformation in transform.transform(self, entry):
                entries.append(transformation)

        return entries


class VocabularyIndexBuilderFromVocabdb(VocabularyIndexBuilder):
    def __init__(self, vocabdb: Vocabdb, book_id: str, db_path = Path('vindex.db')) -> None:
        super().__init__()
        self.__db_path = db_path
        self.__vocabdb = vocabdb
        self.__book_id = book_id

    def build(self) -> VocabularyIndex:
        vocabulary = {}

        with self.__vocabdb as vocabdb:
            book_words = vocabdb.get_words(book_id=self.__book_id)
            for lookup in vocabdb.get_lookups(book_id=self.__book_id).values():
                word = book_words[lookup.word_id]
                if word.lang == self._from_lang:
                    usage = lookup.usage.replace('\u2019', "'")
                    usage_word_index = usage.find(word.value)

                    if usage_word_index == -1:
                        raise ValueError(f'Word "{word.value}" not found in usage "{usage}"')

                    vocabulary[word.value] = {
                        'usage': usage,
                        'usage_word_index': usage_word_index,
                    }

            return VocabularyIndexBuilderFromDict(vocabulary=vocabulary, 
                                                  db_path=self.__db_path)\
                                                  .set_from_lang(self._from_lang)\
                                                  .set_to_lang(self._to_lang)\
                                                  .set_translator(self._translator)\
                                                  .set_transforms(self._transforms)\
                                                  .build()


class VocabularyIndexBuilderFromCSV(VocabularyIndexBuilder):
    def __init__(self, csv_path: Path, db_path = Path('vindex.db')) -> None:
        super().__init__()
        self.__db_path = db_path
        self.__csv_path = csv_path

    def build(self) -> VocabularyIndex:
        if not self.__csv_path.is_file():
            raise ValueError("Input file doesn't exists")
        if self.__csv_path.suffix != '.csv':
            raise ValueError('Expected an input csv')

        # Build a dictionary in the for of: {word: usage found in the book}
        vocabulary = {}
        with open(str(self.__csv_path), encoding='utf-8') as file:
            for line in file:
                word, usage = line.split('\t')
                usage_word_index = usage.find(word)

                if usage_word_index == -1:
                    raise ValueError(f'Word "{word}" not found in usage "{usage}"')

                vocabulary[word] = {
                    'usage': usage,
                    'usage_word_index': usage_word_index,
                }

        return VocabularyIndexBuilderFromDict(vocabulary=vocabulary, 
                                              db_path=self.__db_path)\
                                              .set_from_lang(self._from_lang)\
                                              .set_to_lang(self._to_lang)\
                                              .set_translator(self._translator)\
                                              .set_transforms(self._transforms)\
                                              .build()
