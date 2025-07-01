import lancedb
from lancedb.pydantic import Vector, LanceModel

class PersonModel(LanceModel):
    name: str
    age: int
    vector: Vector[2]

# for testing purposes, create a LanceDB database and table
url = "./example"
db = lancedb.connect(url)
table = db.create_table("person", schema=PersonModel)
table.add(
    [
        PersonModel(name="bob", age=1, vector=[1.0, 2.0]),
        PersonModel(name="alice", age=2, vector=[3.0, 4.0]),
    ]
)
assert table.count_rows() == 2
person = table.search([0.0, 0.0]).limit(1).to_pydantic(PersonModel)
assert person[0].name == "bob"