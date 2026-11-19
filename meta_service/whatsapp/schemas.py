import re
from enum import StrEnum
from typing import Annotated, Any, Literal, Self

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    model_validator,
)

TEXT_LIMIT = 4096
CAPTION_LIMIT = 1024
MAX_RECIPIENTS = 50

_PHONE_RE = re.compile(r"^\+[1-9]\d{1,14}$")
_TEMPLATE_NAME_RE = re.compile(r"^[a-z0-9_]{1,512}$")
_LANGUAGE_RE = re.compile(r"^[a-zA-Z]{2,3}(?:_[a-zA-Z]{2})?$")
_PARAM_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")

_MIME_PREFIXES: dict[str, tuple[str, ...]] = {
    "image": ("image/",),
    "video": ("video/",),
    "audio": ("audio/",),
    "document": ("application/", "text/"),
}


def _check_phone(value: str) -> str:
    phone = value.strip()
    if not _PHONE_RE.fullmatch(phone):
        raise ValueError("phone numbers must be in E.164 format, e.g. +16505551234")
    return phone


PhoneNumber = Annotated[str, AfterValidator(_check_phone)]


class MessageType(StrEnum):
    TEXT = "text"
    TEMPLATE = "template"
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    DOCUMENT = "document"


class TextMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal[MessageType.TEXT]
    body: str = Field(min_length=1, max_length=TEXT_LIMIT)
    preview_url: bool = False


class TemplateMediaObject(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str | None = None
    link: HttpUrl | None = None

    @model_validator(mode="after")
    def _one_source(self) -> Self:
        if (self.id is None) == (self.link is None):
            raise ValueError("provide exactly one of 'id' or 'link'")
        return self


class TemplateParameter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["text", "image", "document", "payload"] = "text"
    text: str | None = None
    parameter_name: str | None = None
    image: TemplateMediaObject | None = None
    document: TemplateMediaObject | None = None
    payload: str | None = None


class TemplateComponent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["header", "body", "footer", "button"]
    sub_type: str | None = None
    index: int | None = Field(default=None, ge=0)
    parameters: list[TemplateParameter] = Field(min_length=1)


class TemplateMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal[MessageType.TEMPLATE]
    name: str = Field(pattern=_TEMPLATE_NAME_RE.pattern)
    language: str = Field(pattern=_LANGUAGE_RE.pattern)
    components: list[TemplateComponent] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_components(self) -> Self:
        names = [
            parameter.parameter_name
            for component in self.components
            for parameter in component.parameters
            if parameter.parameter_name
        ]
        has_positional = any(
            parameter.parameter_name is None
            for component in self.components
            for parameter in component.parameters
        )
        if names and has_positional:
            raise ValueError(
                "a template request cannot mix named and positional parameters"
            )
        if len(set(names)) != len(names):
            raise ValueError("template parameter names must be unique")
        for name in names:
            if not _PARAM_NAME_RE.fullmatch(name):
                raise ValueError(
                    f"invalid template parameter name {name!r}; use lowercase"
                    " letters, digits and underscores"
                )

        for component in self.components:
            if component.type == "button" and (
                component.sub_type is None or component.index is None
            ):
                raise ValueError("button components require 'sub_type' and 'index'")
            for parameter in component.parameters:
                if component.type == "body" and parameter.type != "text":
                    raise ValueError("body parameters must have type 'text'")
                if parameter.type == "text" and parameter.text is None:
                    raise ValueError("text parameters require 'text'")
                if parameter.type == "payload" and parameter.payload is None:
                    raise ValueError("payload parameters require 'payload'")
                if parameter.type == "image" and parameter.image is None:
                    raise ValueError("image parameters require 'image'")
                if parameter.type == "document" and parameter.document is None:
                    raise ValueError("document parameters require 'document'")
        return self


class _MediaMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: HttpUrl | None = None
    media_id: str | None = None
    mime_type: str | None = None
    filename: str | None = None

    @model_validator(mode="after")
    def _check_source(self) -> Self:
        if (self.url is None) == (self.media_id is None):
            raise ValueError("provide exactly one of 'url' or 'media_id'")
        if self.media_id is not None and not self.media_id.strip():
            raise ValueError("'media_id' must not be empty")
        if self.mime_type:
            prefixes = _MIME_PREFIXES[self.type.value]
            if not self.mime_type.lower().startswith(prefixes):
                raise ValueError(
                    f"'mime_type' for {self.type.value} must start with"
                    f" {', '.join(prefixes)}"
                )
        return self


class ImageMessage(_MediaMessage):
    type: Literal[MessageType.IMAGE]
    caption: str | None = Field(default=None, max_length=CAPTION_LIMIT)


class VideoMessage(_MediaMessage):
    type: Literal[MessageType.VIDEO]
    caption: str | None = Field(default=None, max_length=CAPTION_LIMIT)


class AudioMessage(_MediaMessage):
    type: Literal[MessageType.AUDIO]


class DocumentMessage(_MediaMessage):
    type: Literal[MessageType.DOCUMENT]
    caption: str | None = Field(default=None, max_length=CAPTION_LIMIT)
    filename: str = Field(min_length=1)


Message = Annotated[
    TextMessage
    | TemplateMessage
    | ImageMessage
    | VideoMessage
    | AudioMessage
    | DocumentMessage,
    Field(discriminator="type"),
]


class PublishRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    to: list[PhoneNumber] = Field(min_length=1, max_length=MAX_RECIPIENTS)
    message: Message
    reply_to: str | None = None


class MessageReceipt(BaseModel):
    to: str
    wa_id: str | None = None
    message_id: str
    message_status: str | None = None


class SendFailure(BaseModel):
    to: str
    error: str
    code: int | None = None
    subcode: int | None = None
    fbtrace_id: str | None = None


class PublishResult(BaseModel):
    messages: list[MessageReceipt]
    failures: list[SendFailure]
    media_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class PhoneProfile(BaseModel):
    id: str | None = None
    verified_name: str | None = None
    display_phone_number: str | None = None
    status: str | None = None
    messaging_limit: str | None = None


class TemplateSummary(BaseModel):
    id: str
    name: str
    language: str
    category: str | None = None
    status: str | None = None
    parameter_format: str | None = None
