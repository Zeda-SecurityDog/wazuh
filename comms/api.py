from fastapi import APIRouter, Depends, HTTPException, status
from hmac import compare_digest
import opensearchpy
from typing import Annotated

from auth import JWTBearer, generate_token, decode_token
from commands_manager import commands_manager
from models import StatelessEventsBody, Login, GetCommandsResponse, TokenResponse, Message
from opensearch import create_indexer_client, INDEX_NAME

router = APIRouter(prefix="/api/v1")

indexer_client = create_indexer_client()


@router.post("/login")
async def login(login: Login):
    try:
        data = indexer_client.get(index=INDEX_NAME, id=login.uuid)
    except opensearchpy.exceptions.NotFoundError:
        raise HTTPException(status.HTTP_403_FORBIDDEN, Message(message="UUID not found"))

    if not compare_digest(data["_source"]["key"], login.key):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, Message(message="Invalid Key"))

    token = generate_token(login.uuid)
    return TokenResponse(token=token)

@router.post("/events/stateless", dependencies=[Depends(JWTBearer())])
async def post_stateless_events(body: StatelessEventsBody):
    # TODO: send event to the engine
    _ = body.events
    return Message(message="Events received")

@router.get("/commands")
async def get_commands(token: Annotated[str, Depends(JWTBearer())]) -> GetCommandsResponse:
    uuid = decode_token(token)["uuid"]
    commands = await commands_manager.get_commands(uuid)
    if commands:
        return GetCommandsResponse(commands=commands)
    else:
        raise HTTPException(status.HTTP_408_REQUEST_TIMEOUT, Message(message="No commands found"))
