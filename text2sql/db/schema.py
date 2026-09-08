from dataclasses import dataclass


@dataclass(frozen=True)
class Column:
    name: str
    type: str
    primary_key: bool = False
    nullable: bool = True


@dataclass(frozen=True)
class ForeignKey:
    column: str
    target_table: str
    target_column: str


@dataclass(frozen=True)
class TableSchema:
    name: str
    columns: tuple[Column, ...]
    foreign_keys: tuple[ForeignKey, ...] = ()
    description: str = ""

    def text(self, available: set[str] | None = None) -> str:
        lines = [f"Table: {self.name}", f"Description: {self.description}", "Columns:"]
        for c in self.columns:
            suffix = " PRIMARY KEY" if c.primary_key else ""
            lines.append(f"- {c.name} {c.type}{suffix}")
        for fk in self.foreign_keys:
            if available is None or fk.target_table in available:
                lines.append(f"FK: {self.name}.{fk.column} -> {fk.target_table}.{fk.target_column}")
        return "\n".join(lines)


def schema_context(tables: list[TableSchema]) -> str:
    names = {t.name for t in tables}
    return "\n\n".join(t.text(names) for t in tables)
