from typing import Union
import genanki # type: ignore
import re
from pathlib import Path
import json
import hashlib
import argparse
import base64

from anki_notes import NoteBuilder, DeckBuilder
from vindex import VocabularyEntry, VocabularyIndex, VocabularyIndexBuilderFromCSV, VocabularyIndexBuilderFromVocabdb
from vindex_en_utils import PhrasalVerbsTransform, WordReferenceTranslator
from vocabdb import Vocabdb


class KindleNoteBuilder(NoteBuilder):
    def __init__(self, model_name: str, front: Path, back: Path, style: Path) -> None:
        front_text = front.read_text(encoding='utf-8')
        back_text = back.read_text(encoding='utf-8')
        style_text = style.read_text(encoding='utf-8')
        fields = self.__find_fields(front_text + back_text)        
        
        super().__init__(
            model_name=model_name,
            fields=fields,
            templates=[
                {
                    'name': 'card',
                    'qfmt': front_text,
                    'afmt': back_text,
                }
            ],
            style=style_text
        )
    
    @staticmethod
    def __find_fields(text: str) -> list[str]:
        matches = set(re.findall(r'{{(.*?)}}', text))
        matches.discard('FrontSide')
        matches.discard('BackSide')        
        return list(matches)
    
    def build(self, note: dict) -> genanki.Note:
        entry: VocabularyEntry = note['entry']

        if entry.word is None:
            raise ValueError('Entry without word')
        
        if entry.translator is None:
            raise ValueError(f'Entry without translator')
        
        if entry.translator != WordReferenceTranslator.KEY:
            raise ValueError(f'Translators other than {WordReferenceTranslator.KEY} not supported')
        

        if entry.translation is None:
            entry.translation = '{}'

        translation = json.loads(entry.translation)
        return super().build({
            'id': int(hashlib.shake_256(entry.word.encode(encoding='utf-8')).hexdigest(7), base=16), 
            'values': {
                'word': entry.word,
                'pronunciation': self._get_pronunciation(translation),
                'meanings': self._get_meanings(translation),
                'usage': self._get_usage(entry),
                'notes': self._get_notes(entry),
                'url': self._get_url(translation), 
            }
        })

    @classmethod
    def _get_pronunciation(self, translation: dict) -> str:
        if 'pronunciations' not in translation:
            return ''

        pronunciation = ''
        for entry in translation['pronunciations']:
            pronunciation += f'<span class="pronunciation">{entry[0]}</span> <span class="ipa">{", ".join(entry[1])}</span></br>'
        return pronunciation
    
    @classmethod
    def _get_meanings(self, translation: dict) -> str:
        if 'translations' not in translation:
            return ''

        meanings = ''
        for translation in translation['translations']:
            # if translation['title'] == 'Principal Translations':
            for entry in translation['entries']:
                meanings += f'<span class="en gray01">{entry["from_word"]["source"]} => ({entry["context"]})</span></br>'
                for word in entry['to_word']:
                    meanings += f'<span class="es cyan meaning">{word["meaning"]}</span></br>'
                meanings += '</br>'
            
                from_example = entry["from_example"]
                to_example = entry["to_example"]
                
                if from_example is not None:
                    meanings += f'<span class="en ensentence gray02">{from_example}</span></br>'
                if to_example is not None and len(to_example) > 0:
                    to_example = to_example[0]
                    meanings += f'<span class="es essentence gray00">{to_example}</span></br>'
                meanings += '</br>'
        return meanings

    @classmethod
    def _get_url(self, translation: dict) -> str:
        return translation.get('url', '')

    @classmethod
    def _get_usage(self, entry: VocabularyEntry) -> str:
        if entry.usage is None:
            return ''
        
        return entry.usage
    
    @classmethod
    def _get_notes(self, entry: VocabularyEntry) -> str:
        return ''


def book_id_encode(book_id: str) -> str:
    return base64.urlsafe_b64encode(bytes(book_id, 'utf-8')).decode(encoding="utf-8")


def book_id_decode(book_id: str) -> str:
    return base64.urlsafe_b64decode(bytes(book_id, 'utf-8')).decode(encoding="utf-8")


if __name__ == '__main__':
    args_parser = argparse.ArgumentParser()
    args_parser.add_argument('--name', help='Anki deck name, defaults to Unknown')
    args_parser.add_argument('--input', default='vocab.db', help='Vocabulary input file (db or csv)')
    args_parser.add_argument('--book-id', help='If the input file is a kindle vocabulary database you must select the book with this option')
    args_parser.add_argument('--index', default='./vindex.db', help='Generated vocabulary index')
    args_parser.add_argument('--note_template_dir', default='note_template', help='Note styling directory with front.html, back.html and style.css files')
    args_parser.add_argument('--output', default='vocabulary.apkg', help='The output anki deck file name')
    args_parser.add_argument('--to_lang', default='es', help='The language into which to translate the vocabulary')
    args_parser.add_argument('--clear_index', action='store_true')
    args = args_parser.parse_args()
    
    vocabulary_file_path = Path(args.input)

    if not vocabulary_file_path.is_file():
        raise ValueError(f'Could not open vocabulary file "{args.input}"')  
    
    index_builder: Union[VocabularyIndexBuilderFromCSV, VocabularyIndexBuilderFromVocabdb]

    if vocabulary_file_path.suffix == '.csv':
        index_builder = VocabularyIndexBuilderFromCSV(csv_path=vocabulary_file_path)
    elif vocabulary_file_path.suffix == '.db':
        vocabdb = Vocabdb(vocabulary_file_path)
    
        if args.book_id is None:
            print('No book id given, listing all available books:')
            with vocabdb as db:
                for book in db.get_books().values():
                    print(f'id: {book_id_encode(book.id)}, title: {book.title}')
            exit(0)
        else:
            args.book_id = book_id_decode(args.book_id)
            if args.name is None:
                with vocabdb as db:
                    for book in db.get_books().values():
                        if book.id == args.book_id:
                            args.name = f'{book.title}.apkg'

        index_builder = VocabularyIndexBuilderFromVocabdb(vocabdb=vocabdb, 
                                                          book_id=args.book_id)
    else:
        raise ValueError('Unexpected input file type, expected types are .db or .csv')
    
    if args.name is None:
        args.name = 'vocabulary.apkg'

    note_template_dir = Path(args.note_template_dir)
    if not note_template_dir.exists() or not note_template_dir.is_dir():
        raise ValueError(f'Could not open note template directory "{args.note_template_dir}"')
    
    index_path = Path(args.index)

    if args.clear_index:
        index_path.unlink()

    with index_builder\
        .set_from_lang('en')\
        .set_to_lang(args.to_lang)\
        .add_transform(PhrasalVerbsTransform())\
        .set_translator(WordReferenceTranslator(to_lang=args.to_lang))\
        .build() as index:

        DeckBuilder(
            deck_name=f'Kindle Vocabulary - {args.name}', 
            note_builder=KindleNoteBuilder(
                model_name='Kindle Vocabulary Note Type',
                front=note_template_dir.joinpath('front.html'),
                back=note_template_dir.joinpath('back.html'),
                style=note_template_dir.joinpath('style.css')
            ),
        )\
        .set_notes(list(map(lambda entry: {'entry': entry}, index.read_entries())))\
        .build_and_persist(Path(args.output))
