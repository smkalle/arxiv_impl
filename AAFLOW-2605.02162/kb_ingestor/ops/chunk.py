from __future__ import annotations

import pyarrow as pa
import pyarrow.compute as pc

from kb_ingestor.models import IngestConfig


def chunk(table: pa.Table, config: IngestConfig) -> pa.Table:
    text_input = pc.binary_join_element_wise(
        pc.fill_null(pc.cast(table.column("subject"), pa.string()), ""),
        pc.fill_null(pc.cast(table.column("description"), pa.string()), ""),
        " ",
    )
    chunk_col = pc.utf8_slice_codeunits(text_input, start=0, stop=config.max_chunk_chars)
    chunk_len = pc.utf8_length(chunk_col)
    keep_mask = pc.greater_equal(chunk_len, pa.scalar(config.min_chunk_chars, type=pa.int32()))

    chunk_index = pa.array([0] * table.num_rows, type=pa.int32())
    with_chunk = table.append_column("chunk", chunk_col).append_column("chunk_index", chunk_index)
    return with_chunk.filter(keep_mask)
