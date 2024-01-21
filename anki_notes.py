import genanki
from pathlib import Path
from abc import ABC, abstractmethod

class NoteBuilder:
    def __init__(self, model: genanki.Model) -> None:
       self.__model = model
       self.__fields = [field['name'] for field in model.fields]
    
    def build_field_list_for(self, d: dict):
        l = [None for _ in range(len(self.__fields))]
        for k, v in d.items():
            l[self.__fields.index(k)] = v

        if None in l:
            indices = [index for index, value in enumerate(l) if value is None]
            missing_fields = [self.__fields[index] for index in indices]
            raise ValueError(f'Not all fields are present, missing fields: {missing_fields}')

        return l

    def model(self) -> genanki.Model:
        return self.__model

    def build(self, note_id: int, values: dict) -> genanki.Note:
        return genanki.Note(guid=note_id, model=self.model(), fields=self.build_field_list_for(values))

class DeckBuilder(ABC):
    def __init__(self, deck_id: int, deck_name: str, note_builder: NoteBuilder) -> None:
        self.__deck_id = deck_id
        self.__deck_name = deck_name
        self.__note_builder = note_builder

    def note_builder(self) -> NoteBuilder:
        return self.__note_builder

    @abstractmethod
    def build_notes(self) -> [genanki.Note]:
        pass

    def build(self, collection: Path) -> None:
        deck = genanki.Deck(self.__deck_id, self.__deck_name)  

        for note in self.build_notes():
            deck.add_note(note)

        genanki.Package([deck]).write_to_file(str(collection.name))