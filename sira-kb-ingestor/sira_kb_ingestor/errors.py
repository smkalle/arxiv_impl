class SiraIngestorError(Exception):
    """Base error for sira-kb-ingestor."""


class IngestSchemaError(SiraIngestorError):
    pass


class IngestNullError(SiraIngestorError):
    pass


class EmbedModelError(SiraIngestorError):
    pass


class EmbedDimMismatchError(SiraIngestorError):
    pass


class ArtifactBuildError(SiraIngestorError):
    pass


class EnrichmentError(SiraIngestorError):
    pass


class RetrievalError(SiraIngestorError):
    pass
