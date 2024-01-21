import json
from pathlib import Path
import hashlib
from wrpy import WordReference
from vocabdb import Vocabdb


def build_vocabulary_index_with_translations_from_csv(input_file: Path, index_dir_path: Path, to_lang: str = 'es'):
    if not input_file.is_file():
        raise ValueError("Input file doesn't exists")
    if input_file.suffix != '.csv':
        raise ValueError('Expected an input csv')
    if not index_dir_path.is_dir():
        raise ValueError('Expected an output directory, not a file')

    # Build a dictionary in the for of: {word: example found in the book}
    vocabulary = {}
    with open(str(input_file), encoding='utf-8') as input_file:
        for line in input_file:
            values = line.split('\t')
            vocabulary[values[0].strip()] = values[1]
    
    build_vocabulary_index_with_translations_from_dict(vocabulary, index_dir_path, to_lang)


def build_vocabulary_index_with_translations_from_db(book_id: str, db: Vocabdb, index_dir_path: Path, to_lang: str = 'es'):
    vocabulary = {}
    book_words = db.get_words(book_id=book_id)
    for lookup in db.get_lookups(book_id=book_id).values():
        word = book_words[lookup.word_id]
        if word.lang == 'en':
            vocabulary[word.stem] = lookup.usage

    build_vocabulary_index_with_translations_from_dict(vocabulary, index_dir_path, to_lang)


def build_vocabulary_index_with_translations_from_dict(vocabulary: dict, index_dir_path: Path, to_lang: str = 'es'):
    wr = WordReference('en', to_lang)
    words_output_file_path = Path(index_dir_path).joinpath('index.csv')
    translation_output_dir_path = Path(index_dir_path).joinpath('translations')
    translation_output_dir_path.mkdir(exist_ok=True)
    
    # Builds hte word id dictionary and detects collisions in the id generation
    words_ids = {}
    for word in vocabulary.keys():
        word_id = hashlib.shake_256(word.encode(encoding='utf-8')).hexdigest(48)
        
        if word_id in words_ids.keys():
            raise ValueError(f'Collision detected in hashing algorithm for word "{word}", with word "{words_ids[word_id]}"')

        words_ids[word_id] = word
    words_ids = { v: k for k, v in words_ids.items() }

    # Persist the index
    with open(str(words_output_file_path), mode='w', encoding='utf-8') as input_file:
        for word, example in vocabulary.items():
            input_file.write(f'{words_ids[word]}\t{word}\t{example}\n')

    # Words traduction
    total_words = len(vocabulary)
    current_index = 1
    for word, example in vocabulary.items():
        print(f'Translating {current_index}/{total_words}')
        translation_file_path = translation_output_dir_path.joinpath(f'{words_ids[word]}.json')
        
        if translation_file_path.is_file():
            translation = json.loads(translation_file_path.read_text(encoding='utf-8'))
            if translation['word'] != word:
                print(f'Outdated translation or collision found, removing translation file {str(translation_file_path)}')
            else:            
                print(f'Reusing translation for word "{word}" from "{str(translation_file_path)}"')
                current_index += 1
                continue

        translation = json.dumps(wr.translate(word))
        with open(str(translation_file_path), mode='w', encoding='utf-8') as input_file:    
            input_file.write(translation)
        
        current_index += 1
