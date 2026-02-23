# Checking the Weather

To check the weather at a specified location, use curl with the wttr.in service:

```bash
curl wttr.in/<location>?format=3
```

Replace `<location>` with a city name, airport code, or coordinates. Examples:
- `curl wttr.in/London?format=3` - Current weather in London
- `curl wttr.in/SFO?format=3` - Weather at San Francisco airport
- `curl wttr.in/37.7749,-122.4194?format=3` - Weather at specific coordinates

For a more detailed forecast, omit the format parameter:
```bash
curl wttr.in/<location>
```

## Guidelines

- Always ask the user for their location if not specified
- Handle errors gracefully (network issues, invalid locations)
