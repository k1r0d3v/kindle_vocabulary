import json
from typing import Optional
from wrpy import WordReference # type: ignore
import spacy
from spacy.matcher import Matcher
from spacy.util import filter_spans
from vindex import VocabularyEntry, VocabularyIndexBuilder, VocabularyEntryTranslator, VocabularyEntryTransform


class PhrasalVerbsTransform(VocabularyEntryTransform):
    def __init__(self) -> None:
        super().__init__()
        self.__nlp = spacy.load('en_core_web_sm')

    def transform(self, builder: VocabularyIndexBuilder, entry: VocabularyEntry) -> list[VocabularyEntry]:
        if builder._from_lang != 'en':
            raise ValueError('PhrasalVerbsTransform only supports english')
        
        if entry.usage is None:
            print(f'Word "{entry.word}" has no usage, skipping phrasal verbs search')
            return [entry]

        doc = self.__nlp(entry.usage)
        word_span = None
        for token in doc:
            if token.idx == entry.usage_word_index:
                word_span = doc[token.i]

        if word_span is None:
            raise ValueError(f'Word "{entry.word}" not found in usage tokens. You must provide a correct word usage index.')
        
        entry.word = word_span.lemma_

        phrasal_verbs = []
        for token in doc:
            # Check if the token is a verb
            if token.pos_ == "VERB":
                # Check if the token has a particle (preposition or adverb) attached
                if any(child.dep_ == "prt" for child in token.children):
                    # Construct the phrasal verb by concatenating the token and its particle
                    phrasal_verb = token.lemma_ + " " + " ".join([child.lemma_ for child in token.children if child.dep_ == "prt"])
                    phrasal_verbs.append((phrasal_verb, token.i))

        # Discover phrasal verbs
        matcher = Matcher(self.__nlp.vocab)       
        matcher.add('phrasal_verbs', [
            [{'POS': 'VERB'},
            {'POS': 'ADV'},
            {'POS': 'VERB'}],
            [{'POS': 'VERB'},
            {'POS': 'ADV'}],
            [{'POS': 'ADP'},
            {'POS': 'VERB'}],
        ])

        # TODO:
        # noun phrase: r’<DET>? (<NOUN>+ <ADP|CONJ>)* <NOUN>+’ 
        # compound nouns: r’<NOUN>+’ 
        # verb phrase: r’<VERB>?<ADV>*<VERB>+’ 
        # prepositional phrase: r’<PREP> <DET>? (<NOUN>+<ADP>)* <NOUN>+’

        match_spans = [doc[start:end] for _, start, end in matcher(doc)]
        for span in filter_spans(match_spans):
            phrasal_verbs.append((token.lemma_, span.start_char))

        entries = []
        for (phrasal_verb, index) in phrasal_verbs:
            if phrasal_verb != entry.word and phrasal_verb.find(entry.word) != -1:
                new_entry = entry.copy()
                new_entry.word = phrasal_verb
                new_entry.usage_word_index = index
                entries.append(new_entry)

                print(f'[PhrasalVerbsTransform] Found "{entry.word}" in phrasal verb "{phrasal_verb}", usage: {entry.usage}')
        if len(entries) == 0:
            entries.append(entry)

        return entries

class WordReferenceTranslator(VocabularyEntryTranslator):
    KEY = 'word_reference'

    def __init__(self, to_lang, force_update = False) -> None:
        super().__init__()
        self.to_lang = to_lang
        self.force_update = force_update

    def key(self) -> str:
        return WordReferenceTranslator.KEY

    def translate(self, entry: VocabularyEntry) -> Optional[str]:
        print(f'[WordReferenceTranslator] Translating "{entry.word}"')
        wr = WordReference(from_lang=entry.lang, to_lang=self.to_lang)

        try:
            return json.dumps(wr.translate(entry.word))
        except NameError:
            print(f'[WordReferenceTranslator] Could no translate "{entry.word}"')
            return None

    def should_update(self, newEntry: VocabularyEntry, oldEntry: VocabularyEntry) -> bool:
        if oldEntry.translator != WordReferenceTranslator.KEY or oldEntry.translation is None:
            return True
        
        if self.force_update:
            return True
        
        return False 
