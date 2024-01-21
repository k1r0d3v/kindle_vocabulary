import genanki
import re
from pathlib import Path
import json
import hashlib
import argparse
import base64

import anki_notes
import index_builder
import vocabdb


class KindleNoteBuilder(anki_notes.NoteBuilder):
    def __init__(self, model_name: str, front: Path, back: Path, css: Path) -> None:
        front = front.read_text(encoding='utf-8')
        back = back.read_text(encoding='utf-8')
        fields = set(re.findall(r'{{(.*?)}}', front + back))
        fields.discard('FrontSide')
        fields.discard('BackSide')        
        fields = list(fields)
        
        model_id=int(hashlib.shake_256(model_name.encode(encoding='utf-8')).hexdigest(7), base=16)
        
        super().__init__(genanki.Model(
            model_id=model_id, 
            name=model_name,
            fields=[{'name': field } for field in fields],
            templates=[
                {
                    'name': 'card',
                    'qfmt': front,
                    'afmt': back,
                }
            ],
            css=css.read_text(encoding='utf-8')
        ))


class KindleDeckBuilder(anki_notes.DeckBuilder):
    def __init__(self, deck_name: str, index_dir_path: Path, note_builder: anki_notes.NoteBuilder) -> None:
        deck_id=int(hashlib.shake_256(deck_name.encode(encoding='utf-8')).hexdigest(7), base=16)
        
        super().__init__(deck_id, deck_name, note_builder)
        self.__index_dir_path = index_dir_path
    
    def build_notes(self) -> [genanki.Note]:
        notes = []
        
        with open(str(self.__index_dir_path.joinpath('index.csv')), encoding='utf-8') as file:
            processed_words = {}
            for line in file:
                id, word, example = line.split('\t')
                translation = json.loads(self.__index_dir_path.joinpath(Path('translations', f'{id}.json')).read_text(encoding='utf-8'))
                
                note_id = int(hashlib.shake_256(id.encode(encoding='utf-8')).hexdigest(7), base=16)
                if note_id in processed_words.keys():
                    raise ValueError(f'Collision found while generating a note identifier of 7 bytes for word "{word}" with word "{processed_words[note_id]}"')
                
                notes.append(self.note_builder().build(note_id, {
                    'word': word, 
                    'pronunciation': KindleDeckBuilder.__get_pronunciation(translation),
                    'meanings': KindleDeckBuilder.__get_meanings(translation),
                    'example': example,
                    'notes': '',
                    'word_reference': translation['url'], 
                }))
        
        return notes
    
    
    @staticmethod
    def __get_pronunciation(translation) -> str:
        pronunciation = ''
        for entry in translation['pronunciations']:            
            pronunciation += f'<span class="pronunciation">{entry[0]}</span> <span class="ipa">{", ".join(entry[1])}</span></br>'
        return pronunciation
    
    @staticmethod
    def __get_meanings(translation) -> str:
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


def rmdir(directory: Path):
    for item in directory.iterdir():
        if item.is_dir():
            rmdir(item)
        else:
            item.unlink()
    directory.rmdir()


if __name__ == '__main__':
    args_parser = argparse.ArgumentParser()
    args_parser.add_argument('--name', help='Anki deck name, defaults to Unknown')
    args_parser.add_argument('--input', default='vocab.db', help='Vocabulary input file (db or csv)')
    args_parser.add_argument('--book_id', help='If the input file is a kindle vocabulary database you must select the book with this option')
    args_parser.add_argument('--index_dir', default='.vindex', help='Index directory where store the temporal generated files')
    args_parser.add_argument('--note_template_dir', default='note_template', help='Note styling directory with front.html, back.html and style.css files')
    args_parser.add_argument('--output', default='vocabulary.apkg', help='The output anki deck file name')
    args_parser.add_argument('--to_lang', default='es', help='The language into which to translate the vocabulary')
    args_parser.add_argument('--clear_index', action='store_true')
    args = args_parser.parse_args()
    
    index_dir_path = Path(args.index_dir)
    index_dir_path.mkdir(exist_ok=True)

    vocabulary_file_path = Path(args.input)
    if not vocabulary_file_path.is_file():
        raise ValueError(f'Could not open vocabulary file "{args.input}"')  
    
    if vocabulary_file_path.suffix == '.csv':
        index_builder.build_vocabulary_index_with_translations_from_csv(vocabulary_file_path, index_dir_path, args.to_lang)
    elif vocabulary_file_path.suffix == '.db':
        with vocabdb.Vocabdb(vocabulary_file_path) as db:
            if args.book_id is None:
                print('No book id given, listing all available books:')
                for book in db.get_books().values():
                    print(f'id: {book.id}, title: {book.title}')
                exit(0)
            else:
                if args.name is None:
                    for book in db.get_books().values():
                        if book.id == args.book_id:
                            args.name = f'{book.title}.apkg'

                index_builder.build_vocabulary_index_with_translations_from_db(args.book_id, db, index_dir_path, args.to_lang)
    else:
        raise ValueError('Unexpected input file type, expected types are .db or .csv')
    
    if args.name is None:
        args.name = 'vocabulary.apkg'

    note_template_dir = Path(args.note_template_dir)
    if not note_template_dir.exists() or not note_template_dir.is_dir():
        raise ValueError(f'Could not open note template directory "{args.note_template_dir}"')
    
    if args.clear_index:
        rmdir(index_dir_path)

    note_builder = KindleNoteBuilder(
        model_name='Kindle Vocabulary Note Type',
        front=note_template_dir.joinpath('front.html'),
        back=note_template_dir.joinpath('back.html'),
        css=note_template_dir.joinpath('style.css')
    )

    deck_builder = KindleDeckBuilder(
        deck_name=f'Kindle Vocabulary - {args.name}', 
        index_dir_path=index_dir_path,
        note_builder=note_builder
    )

    deck_builder.build(Path(args.output))
