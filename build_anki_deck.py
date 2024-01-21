import genanki
import re
from pathlib import Path
from anki_notes import *
import json
from anki_notes import NoteBuilder
import hashlib
from build_vocabulary_index import *
import argparse


class KindleNoteBuilder(NoteBuilder):
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


class KindleDeckBuilder(DeckBuilder):
    def __init__(self, deck_name: str, index_dir_path: Path, note_builder: NoteBuilder) -> None:
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
            if translation['title'] == 'Principal Translations':
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

if __name__ == '__main__':
    args_parser = argparse.ArgumentParser()
    args_parser.add_argument('name', help='Anki deck name')
    args_parser.add_argument('--input', default='vocabulary.csv', help='Vocabulary input file')
    args_parser.add_argument('--index_dir', default='.vindex', help='Index directory where store the temporal generated files')
    args_parser.add_argument('--note_template_dir', default='note_template', help='Note styling directory with front.html, back.html and style.css files')
    args_parser.add_argument('--output', default='vocabulary.apkg', help='The output anki deck file name')
    args = args_parser.parse_args()
    
    vocabulary_file_path = Path(args.input)
    if not vocabulary_file_path.is_file():
        raise ValueError('Could not open vocabulary file')
    
    index_dir_path = Path(args.index_dir)
    index_dir_path.mkdir(exist_ok=True)
    build_vocabulary_index_with_translations(vocabulary_file_path, index_dir_path)
    
    note_template_dir = Path(args.note_template_dir)
    if not note_template_dir.exists() or not note_template_dir.is_dir():
        raise ValueError('Could not open note template directory')
    
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
