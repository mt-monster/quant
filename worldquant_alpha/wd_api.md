# WorldQuant Brain API

## Update Alpha Properties

### Endpoint

```
PATCH https://api.worldquantbrain.com/alphas/{alpha_id}
```

### Description

Updates the properties of a specific Alpha.

### Parameters

| Name | Type | In | Description |
|------|------|-------|-------------|
| `alpha_id` | string | path | The unique identifier of the Alpha to update |

### Request Body

| Field | Type | Description |
|-------|------|-------------|
| `color` | string | The color of the Alpha |
| `name` | string | The name of the Alpha |
| `tags` | array of strings | Tags associated with the Alpha |
| `category` | string or null | The category of the Alpha |
| `regular.description` | string or null | Description for regular Alpha |
| `combo.description` | string | Description for combo Alpha |
| `selection.description` | string | Description for selection Alpha |

### Example Request

```python
import requests

alpha_id = "your_alpha_id"
params = {
    "color": "blue",
    "name": "My Updated Alpha",
    "tags": ["tag1", "tag2"],
    "category": None,
    "regular": {"description": None},
    "combo": {"description": "Combo description"},
    "selection": {"description": "Selection description"}
}

response = requests.patch(
    f"https://api.worldquantbrain.com/alphas/{alpha_id}",
    json=params
)
```

### Response

- **Status Code**: 200 OK if successful
- **Body**: Updated Alpha object

### Notes

- Authentication is required for this endpoint.
- Only provide the properties you want to update in the request body.