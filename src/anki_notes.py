from typing import Any, Optional, Self
import genanki # type: ignore
from pathlib import Path
import hashlib


class NoteBuilder:
    def __init__(self, model_name: str, fields: list[str], templates: list[dict[str, str]], style: str, model_id: Optional[int] = None) -> None:
        if model_id is None:
            model_id = int(hashlib.shake_256(model_name.encode(encoding='utf-8')).hexdigest(7), base=16)

        self.__model = genanki.Model(
            model_id=model_id,
            name=model_name,
            fields=[{'name': field } for field in fields],
            templates=templates,
            css=style
        )
        self.__fields = [field['name'] for field in self.__model.fields]
    
    def build_field_list_for(self, d: dict[str, str]):
        l: list[Optional[str]] = [None for _ in range(len(self.__fields))]
        for k, v in d.items():
            l[self.__fields.index(k)] = v

        if None in l:
            indices = [index for index, value in enumerate(l) if value is None]
            missing_fields = [self.__fields[index] for index in indices]
            raise ValueError(f'Not all fields are present, missing fields: {missing_fields}')

        return l

    def model(self) -> genanki.Model:
        return self.__model

    def build(self, note: dict) -> genanki.Note:
        return genanki.Note(guid=note['id'], model=self.model(), fields=self.build_field_list_for(note['values']))


class DeckBuilder:
    def __init__(self, deck_name: str, note_builder: NoteBuilder, deck_id: Optional[int] = None, notes: list[dict] = []) -> None:
        if deck_id is None:
            self.__deck_id = int(hashlib.shake_256(deck_name.encode(encoding='utf-8')).hexdigest(7), base=16)
        else:
            self.__deck_id = deck_id
        self.__deck_name = deck_name
        self.__note_builder = note_builder
        self.__notes = notes

    def set_notes(self, notes: list[dict]) -> Self:
        self.__notes = notes
        return self

    def build(self) -> genanki.Deck:
        deck = genanki.Deck(self.__deck_id, self.__deck_name)
        processed_notes: dict[int, genanki.Note] = {}

        for note in self.__notes:
            built_note = self.__note_builder.build(note)
            if built_note.guid in processed_notes.keys():
                raise ValueError(f'Collision found for note "{built_note.fields}" with note "{processed_notes[built_note.guid].fields}"')

            deck.add_note(built_note)
            processed_notes[built_note.guid] = built_note

        return deck

    def build_and_persist(self, path: Path) -> None:
        genanki.Package([self.build()]).write_to_file(str(path.name))