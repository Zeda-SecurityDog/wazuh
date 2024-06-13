## Usage

Run the API using

```
docker compose up
```

The docker compose is configured to run on the port 5000 and generate a command for certain uuids every 10 seconds. If you would like to change these configurations, modify the `command` field flags.

### Run agent-comms-api manually

```
docker build -t agent_comms_api .

docker run -d -p 5000:5000 agent_comms_api
```

### Log in to the API

```
curl -H 'Content-Type: application/json' -s -k -X POST http://localhost:5000/api/v1/login -d '{"uuid":"<UUID>","password":"<PASSWORD>"}'
```

### Get commands

```
curl -H "Authorization: Bearer <TOKEN>" -X GET -k http://localhost:5000/api/v1/commands
```

### Post stateless events

```
curl -H "Authorization: Bearer <TOKEN>" -H "Content-type: application/json" -X POST -k http://localhost:5000/api/v1/events/stateless -d '{"events": [{"id": <ID>,"data": <DATA>, "timestamp": <TIMESTAMP>}]}'
```