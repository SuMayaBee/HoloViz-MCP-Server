---
name: param
description: Building Python classes with validated, typed parameters using the Param library. Covers reactive dependencies, watchers, and configuration patterns.
metadata:
  version: "1.0.0"
  author: holoviz
  category: programming
  difficulty: intermediate
---

# Param: Declarative Parameters

Create typed, validated class attributes with reactive programming support.

## Hello World

```python
# pyright: reportAssignmentType=false
import param

class Greeter(param.Parameterized):
    target: str = param.String(default="World", doc="Name to greet")
    greeting: str = param.Selector(default="Hello", objects=["Hello", "Hi", "Hey"])
    count: int = param.Integer(default=1, bounds=(1, 10))
    history: list = param.List(default=[])

    @param.depends("target", "greeting", "count")
    def message(self) -> str:
        return " ".join([f"{self.greeting}, {self.target}!"] * self.count)

    @param.depends("target", watch=True)
    def _track_changes(self):
        self.history = self.history + [self.target]
```

## Core Parameter Types

```python
import param

class Config(param.Parameterized):
    # Strings
    name: str = param.String(default="unnamed")
    color: str = param.Color(default="#FF5733")

    # Numbers
    count: int = param.Integer(default=10, bounds=(0, 1000))
    rate: float = param.Number(default=0.5, bounds=(0.0, 1.0), step=0.1)

    # Boolean
    enabled: bool = param.Boolean(default=True)

    # Selectors
    mode: str = param.Selector(default="auto", objects=["auto", "manual"])
    tags: list = param.ListSelector(default=["a"], objects=["a", "b", "c"])

    # Collections
    items: list = param.List(default=[], item_type=str)
    config: dict = param.Dict(default={})

    # Dates
    date: datetime.date = param.CalendarDate(default=datetime.date.today())

    # Actions
    submit: bool = param.Event(doc="Trigger processing")
```

## Reactive Dependencies

### watch=False: Computed values (for UI frameworks)

```python
@param.depends("source", "limit")
def get_data(self) -> list:
    return query(self.source, self.limit)
```

### watch=True: Side effects (auto-executed)

```python
@param.depends("continent", watch=True, on_init=True)
def _update_countries(self):
    countries = self._countries[self.continent]
    self.param.country.objects = countries
    if self.country not in countries:
        self.country = countries[0]
```

### on_init=True: Run during instantiation

Always use when initialization depends on parameter values.

## Best Practices

### DO
- Use `param.Parameterized` for production code
- Add type annotations for IDE support
- Add `# pyright: reportAssignmentType=false` at file top
- Use `watch=True` for side effects, `watch=False` for computed values
- Use `on_init=True` when init logic depends on parameter values
- Use `bounds` for numeric constraints
- Use `doc` for documentation

### DON'T
- Use `name` as parameter — it's reserved
- Use `param.bind`/`rx` for production code
- Modify parameters inside their own `watch=True` callbacks (infinite loops)
- Use mutable defaults without `instantiate=True` or `default_factory`

## Testing

```python
def test_computed_values():
    calc = Calculator(a=5, b=3)
    assert calc.result() == 8

def test_reactivity():
    calc = Calculator(a=2, b=3)
    assert calc.result() == 5
    calc.a = 10
    assert calc.result() == 13

def test_validation():
    with pytest.raises(ValueError):
        Calculator(a="not a number")
```

## Common Patterns

### Batch Updates

```python
config.param.update(debug=True, log_level="DEBUG")  # Watchers called once
```

### Serialization

```python
user.param.values(onlychanged=True)
json_str = user.param.serialize_parameters()
```

## Resources

- [Param Documentation](https://param.holoviz.org)
- [Parameter Types](https://param.holoviz.org/user_guide/Parameter_Types.html)
- [Dependencies and Watchers](https://param.holoviz.org/user_guide/Dependencies_and_Watchers.html)
