import asyncio
from typing import List

from fastapi import Request
from pydantic import TypeAdapter

from comms_api.models.events import StatefulEvents
from wazuh.core.engine.base import APPLICATION_JSON
from wazuh.core.engine import get_engine_client
from wazuh.core.exception import WazuhError
from wazuh.core.indexer.base import IndexerKey
from wazuh.core.batcher.client import BatcherClient
from wazuh.core.batcher.mux_demux import MuxDemuxQueue
from wazuh.core.indexer.models.events import AgentMetadata, Header, Operation, StatefulEvent, TaskResult

HTTP_STATUS_OK = 200
HTTP_STATUS_PARTIAL_CONTENT = 206


async def send_stateful_events(events: StatefulEvents, batcher_queue: MuxDemuxQueue) -> List[TaskResult]:
    """Post new events to the batcher.

    Parameters
    ----------
    events : StatefulEvents
        Stateful events.
    batcher_queue : MuxDemuxQueue
        Queue used by the BatcherClient for processing.

    Returns
    -------
    List[TaskResult]
        List of results from the bulk tasks.
    """
    batcher_client = BatcherClient(queue=batcher_queue)
    return await send_events(events=events, batcher_client=batcher_client)


async def send_stateless_events(request: Request) -> None:
    """Send new events to the engine.

    Parameters
    ----------
    request : Request
        Incoming HTTP request.
    
    Raises
    ------
    WazuhError(2708)
        Invalid request headers.
    """
    if request.headers.get('Content-Type') != APPLICATION_JSON or \
            request.headers.get('Transfer-Encoding') != 'chunked':
        raise WazuhError(2708)

    async with get_engine_client() as engine_client:
        await engine_client.events.send(request.stream())


async def parse_stateful_events(request: Request) -> StatefulEvents:
    """Parse stateful events body stream into an object.
    
    Parameters
    ----------
    request : Request
        Incoming HTTP request.
    
    Raises
    ------
    WazuhError(2708)
        Invalid request body headers.
    WazuhError(2709)
        Invalid request body structure.
    
    Returns
    -------
    StatefulEvents
        Object containing the agent metadata, headers and events.
    """
    if request.headers.get('Content-Type') != 'application/json' or \
            request.headers.get('Transfer-Encoding') != 'chunked':
        raise WazuhError(2708)

    i: int = 0
    headers: List[Header] = []
    data: List[StatefulEvent] = []

    async for chunk in request.stream():
        if len(chunk) == 0:
            continue

        parts = chunk.splitlines()

        if len(parts) < 2:
            raise WazuhError(2709)

        for part in parts:
            if len(part) == 0:
                continue

            if i == 0:
                agent_metadata = AgentMetadata.model_validate_json(part)
            elif i % 2 == 0:
                data.append(TypeAdapter(StatefulEvent).validate_json(part))
            else:
                header = Header.model_validate_json(part)
                headers.append(header)
                if header.operation == Operation.DELETE:
                    # Skip the counter increment, we don't expect event data after this header
                    continue

            i += 1

    return StatefulEvents(agent_metadata=agent_metadata, headers=headers, data=data)


async def send_events(events: StatefulEvents, batcher_client: BatcherClient) -> List[TaskResult]:
    """Send events to the batcher.

    Parameters
    ----------
    events : StatefulEvents
        Stateful events.
    batcher_client : BatcherClient
        Client responsible for sending the events to the batcher and managing responses.

    Returns
    -------
    List[TaskResult]
        Indexer response for each one of the bulk tasks.
    """
    tasks: List[asyncio.Task] = []
    i: int = 0

    # Sends the events to the batcher
    for header in events.headers:
        data = None
        if header.operation != Operation.DELETE:
            data = events.data[i]
            i += 1

        batcher_client.send_event(agent_metadata=events.agent_metadata, header=header, data=data)
            
        task = asyncio.create_task(
            (lambda u: batcher_client.get_response(u))(header.id)
        )
        tasks.append(task)

    # Wait for all of them and create response
    tasks_results = await asyncio.gather(*tasks)
    return parse_tasks_results(tasks_results)


def parse_tasks_results(tasks_results: List[dict]) -> List[TaskResult]:
    """Parse tasks results.
    
    Parameters
    ----------
    tasks_results : List[dict]
        Tasks results dictionary list.
    
    Returns
    -------
    results : List[TaskResult]
        Tasks results object list.
    """
    results: List[TaskResult] = []

    for result in tasks_results:
        status = result[IndexerKey.STATUS]
        if status >= HTTP_STATUS_OK and status <= HTTP_STATUS_PARTIAL_CONTENT:
            task_result = TaskResult(id=result[IndexerKey._ID], result=result[IndexerKey.RESULT], status=status)
        else:
            task_result = TaskResult(id='', result=result[IndexerKey.ERROR][IndexerKey.REASON], status=status)

        results.append(task_result)

    return results
