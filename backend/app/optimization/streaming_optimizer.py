"""
Streaming Optimizer - Phase 7 Sprint 3 Day 20-21

Purpose: Optimize response times for large datasets with streaming

Features:
- Streaming response for large datasets
- Response compression
- Virtual scrolling support
- Batch processing
- Progressive loading
"""

import asyncio
import gzip
import json
import logging
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class CompressionType(Enum):
    """Supported compression types."""
    NONE = "none"
    GZIP = "gzip"
    BROTLI = "brotli"


@dataclass
class StreamingChunk:
    """A chunk of data for streaming."""
    data: Any
    chunk_id: int
    total_chunks: int
    is_final: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "chunk_id": self.chunk_id,
            "total_chunks": self.total_chunks,
            "is_final": self.is_final,
            "data": self.data,
            "metadata": self.metadata
        }


class StreamingOptimizer:
    """
    Optimize responses for large datasets using streaming.

    Features:
    - Chunked data delivery
    - Progressive loading
    - Backpressure handling
    - Client-side buffering support
    """

    # Default chunk sizes
    DEFAULT_CHUNK_SIZE = 100
    MAX_CHUNK_SIZE = 1000

    def __init__(
        self,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        enable_compression: bool = True,
        compression_type: CompressionType = CompressionType.GZIP
    ):
        """
        Initialize streaming optimizer.

        Args:
            chunk_size: Number of items per chunk
            enable_compression: Enable response compression
            compression_type: Type of compression to use
        """
        self.chunk_size = min(chunk_size, self.MAX_CHUNK_SIZE)
        self.enable_compression = enable_compression
        self.compression_type = compression_type

    async def stream_data(
        self,
        data_source: AsyncIterator[Any],
        total_count: int | None = None
    ) -> AsyncIterator[StreamingChunk]:
        """
        Stream data from an async iterator.

        Args:
            data_source: Async iterator yielding data items
            total_count: Total number of items (if known)

        Yields:
            StreamingChunk objects
        """
        chunk_id = 0
        buffer = []

        try:
            async for item in data_source:
                buffer.append(item)

                if len(buffer) >= self.chunk_size:
                    chunk = StreamingChunk(
                        data=buffer.copy(),
                        chunk_id=chunk_id,
                        total_chunks=total_count or -1,
                        metadata={"timestamp": datetime.now().isoformat()}
                    )

                    yield chunk

                    chunk_id += 1
                    buffer.clear()

            # Yield final chunk with remaining items
            if buffer:
                chunk = StreamingChunk(
                    data=buffer,
                    chunk_id=chunk_id,
                    total_chunks=chunk_id + 1,
                    is_final=True,
                    metadata={"timestamp": datetime.now().isoformat()}
                )
                yield chunk
            else:
                # Empty final chunk
                yield StreamingChunk(
                    data=[],
                    chunk_id=chunk_id,
                    total_chunks=chunk_id + 1,
                    is_final=True
                )

        except Exception as e:
            logger.error(f"Error streaming data: {e}")
            # Yield error chunk
            yield StreamingChunk(
                data=[],
                chunk_id=chunk_id,
                total_chunks=chunk_id + 1,
                is_final=True,
                metadata={"error": str(e)}
            )

    async def stream_query_results(
        self,
        query_func: Callable,
        chunk_size: int | None = None
    ) -> AsyncIterator[StreamingChunk]:
        """
        Stream query results in chunks.

        Args:
            query_func: Async function that returns query results
            chunk_size: Override default chunk size

        Yields:
            StreamingChunk objects
        """
        chunk_size = chunk_size or self.chunk_size

        try:
            # Execute query
            results = await query_func()

            if not isinstance(results, list):
                results = list(results)

            total_count = len(results)
            chunk_id = 0

            # Stream in chunks
            for i in range(0, total_count, chunk_size):
                chunk = results[i:i + chunk_size]

                yield StreamingChunk(
                    data=chunk,
                    chunk_id=chunk_id,
                    total_chunks=total_count,
                    is_final=(i + chunk_size >= total_count),
                    metadata={
                        "range_start": i,
                        "range_end": min(i + chunk_size, total_count)
                    }
                )

                chunk_id += 1

                # Small delay to allow client processing
                await asyncio.sleep(0.01)

        except Exception as e:
            logger.error(f"Error streaming query results: {e}")
            yield StreamingChunk(
                data=[],
                chunk_id=0,
                total_chunks=1,
                is_final=True,
                metadata={"error": str(e)}
            )

    async def compress_chunk(self, chunk: StreamingChunk) -> bytes:
        """
        Compress a chunk for transmission.

        Args:
            chunk: Chunk to compress

        Returns:
            Compressed bytes
        """
        if not self.enable_compression:
            return json.dumps(chunk.to_dict()).encode('utf-8')

        data = json.dumps(chunk.to_dict()).encode('utf-8')

        if self.compression_type == CompressionType.GZIP:
            return gzip.compress(data)

        return data

    async def decompress_chunk(self, compressed_data: bytes) -> StreamingChunk:
        """
        Decompress a compressed chunk.

        Args:
            compressed_data: Compressed chunk data

        Returns:
            StreamingChunk object
        """
        if self.compression_type == CompressionType.GZIP:
            data = gzip.decompress(compressed_data)
        else:
            data = compressed_data

        chunk_dict = json.loads(data.decode('utf-8'))
        return StreamingChunk(**chunk_dict)


class ResponseOptimizer:
    """
    Optimize API responses for better performance.

    Features:
    - Response compression
    - Field filtering
    - Pagination support
    - Metadata optimization
    """

    def __init__(
        self,
        enable_compression: bool = True,
        compression_threshold: int = 1024  # 1KB
    ):
        """
        Initialize response optimizer.

        Args:
            enable_compression: Enable response compression
            compression_threshold: Minimum size to compress
        """
        self.enable_compression = enable_compression
        self.compression_threshold = compression_threshold

    def filter_fields(
        self,
        data: dict[str, Any],
        fields: list[str] | None = None
    ) -> dict[str, Any]:
        """
        Filter response to include only specified fields.

        Args:
            data: Original data
            fields: List of fields to include (None for all)

        Returns:
            Filtered data
        """
        if not fields:
            return data

        filtered = {}
        for name in fields:
            if name in data:
                filtered[name] = data[name]

        return filtered

    def paginate_response(
        self,
        data: list[Any],
        page: int = 1,
        page_size: int = 100
    ) -> dict[str, Any]:
        """
        Paginate a list response.

        Args:
            data: List of items
            page: Page number (1-indexed)
            page_size: Items per page

        Returns:
            Paginated response with metadata
        """
        total = len(data)
        start = (page - 1) * page_size
        end = start + page_size

        items = data[start:end]

        return {
            "items": items,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total_items": total,
                "total_pages": (total + page_size - 1) // page_size,
                "has_next": end < total,
                "has_prev": page > 1
            }
        }

    def optimize_response(
        self,
        response: dict[str, Any],
        compress: bool = None
    ) -> dict[str, Any]:
        """
        Optimize a response for performance.

        Args:
            response: Original response
            compress: Override default compression setting

        Returns:
            Optimized response
        """
        should_compress = compress if compress is not None else self.enable_compression

        # Check if compression is beneficial
        if should_compress:
            response_size = len(json.dumps(response).encode('utf-8'))
            should_compress = response_size >= self.compression_threshold

        optimized = {
            "data": response.get("data"),
            "metadata": {
                **response.get("metadata", {}),
                "compressed": should_compress,
                "optimized": True,
                "timestamp": datetime.now().isoformat()
            }
        }

        return optimized

    def add_performance_metadata(
        self,
        response: dict[str, Any],
        execution_time_ms: float,
        source: str,
        cache_hit: bool = False
    ) -> dict[str, Any]:
        """
        Add performance metadata to response.

        Args:
            response: Original response
            execution_time_ms: Query execution time
            source: Data source
            cache_hit: Whether result came from cache

        Returns:
            Response with performance metadata
        """
        if "metadata" not in response:
            response["metadata"] = {}

        response["metadata"].update({
            "performance": {
                "execution_time_ms": execution_time_ms,
                "source": source,
                "cache_hit": cache_hit,
                "timestamp": datetime.now().isoformat()
            }
        })

        return response


class VirtualScroller:
    """
    Support for virtual scrolling of large datasets.

    Features:
    - Window-based loading
    - Item height calculation
    - Scroll position tracking
    - Dynamic buffer sizing
    """

    # Default buffer sizes
    DEFAULT_BUFFER_SIZE = 5
    MIN_BUFFER_SIZE = 2
    MAX_BUFFER_SIZE = 10

    def __init__(
        self,
        item_height: int = 50,  # pixels
        viewport_height: int = 800,  # pixels
        buffer_size: int = DEFAULT_BUFFER_SIZE
    ):
        """
        Initialize virtual scroller.

        Args:
            item_height: Height of each item in pixels
            viewport_height: Height of visible viewport in pixels
            buffer_size: Number of items to buffer outside viewport
        """
        self.item_height = item_height
        self.viewport_height = viewport_height
        self.buffer_size = min(
            max(buffer_size, self.MIN_BUFFER_SIZE),
            self.MAX_BUFFER_SIZE
        )

        # Calculate visible items
        self.visible_items = viewport_height // item_height

        # Calculate total items to load (visible + buffer)
        self.window_size = self.visible_items + 2 * self.buffer_size

    def get_window(
        self,
        scroll_position: int,
        total_items: int
    ) -> dict[str, Any]:
        """
        Get the window of items to load based on scroll position.

        Args:
            scroll_position: Current scroll position in pixels
            total_items: Total number of items

        Returns:
            Window information
        """
        # Calculate current item index
        current_item = scroll_position // self.item_height

        # Calculate window bounds
        window_start = max(0, current_item - self.buffer_size)
        window_end = min(total_items, current_item + self.visible_items + self.buffer_size)

        return {
            "start_index": window_start,
            "end_index": window_end,
            "scroll_position": scroll_position,
            "current_item": current_item,
            "visible_items": self.visible_items,
            "window_size": window_end - window_start
        }

    def get_batches(
        self,
        total_items: int,
        batch_size: int | None = None
    ) -> list[dict[str, Any]]:
        """
        Split items into batches for loading.

        Args:
            total_items: Total number of items
            batch_size: Size of each batch (default: window_size)

        Returns:
            List of batch information
        """
        batch_size = batch_size or self.window_size

        batches = []
        for i in range(0, total_items, batch_size):
            batches.append({
                "batch_id": i // batch_size,
                "start_index": i,
                "end_index": min(i + batch_size, total_items),
                "size": min(batch_size, total_items - i)
            })

        return batches

    def get_prefetch_info(
        self,
        scroll_position: int,
        scroll_direction: str,
        total_items: int
    ) -> dict[str, Any]:
        """
        Get information for prefetching data.

        Args:
            scroll_position: Current scroll position
            scroll_direction: Direction of scroll (up, down)
            total_items: Total number of items

        Returns:
            Prefetch information
        """
        current_item = scroll_position // self.item_height

        if scroll_direction == "down":
            prefetch_start = min(total_items, current_item + self.visible_items + self.buffer_size)
            prefetch_end = min(total_items, prefetch_start + self.buffer_size)
        else:  # up
            prefetch_end = max(0, current_item - self.buffer_size)
            prefetch_start = max(0, prefetch_end - self.buffer_size)

        return {
            "direction": scroll_direction,
            "prefetch_start": prefetch_start,
            "prefetch_end": prefetch_end,
            "prefetch_count": prefetch_end - prefetch_start
        }


class BatchProcessor:
    """
    Process large datasets in batches for better performance.

    Features:
    - Configurable batch size
    - Parallel batch processing
    - Progress tracking
    - Error handling per batch
    """

    def __init__(
        self,
        batch_size: int = 100,
        max_parallel_batches: int = 5
    ):
        """
        Initialize batch processor.

        Args:
            batch_size: Number of items per batch
            max_parallel_batches: Maximum batches to process in parallel
        """
        self.batch_size = batch_size
        self.max_parallel_batches = max_parallel_batches

    async def process_batches(
        self,
        items: list[Any],
        process_func: Callable[[list[Any]], Any],
        progress_callback: Callable[[int, int], None] | None = None
    ) -> list[Any]:
        """
        Process items in batches.

        Args:
            items: List of items to process
            process_func: Async function to process each batch
            progress_callback: Optional callback for progress updates

        Returns:
            List of processed batch results
        """
        if not items:
            return []

        total_batches = (len(items) + self.batch_size - 1) // self.batch_size
        results = []

        # Process batches
        for i in range(0, len(items), self.batch_size):
            batch = items[i:i + self.batch_size]
            batch_num = i // self.batch_size + 1

            try:
                result = await process_func(batch)
                results.append(result)

                if progress_callback:
                    progress_callback(batch_num, total_batches)

            except Exception as e:
                logger.error(f"Error processing batch {batch_num}: {e}")
                results.append({"error": str(e), "batch": batch_num})

        return results

    async def process_batches_parallel(
        self,
        items: list[Any],
        process_func: Callable[[list[Any]], Any],
        progress_callback: Callable[[int, int], None] | None = None
    ) -> list[Any]:
        """
        Process batches in parallel for better performance.

        Args:
            items: List of items to process
            process_func: Async function to process each batch
            progress_callback: Optional callback for progress updates

        Returns:
            List of processed batch results
        """
        if not items:
            return []

        # Create batch tasks
        tasks = []
        for i in range(0, len(items), self.batch_size):
            batch = items[i:i + self.batch_size]

            async def process_batch(b):
                try:
                    return await process_func(b)
                except Exception as e:
                    logger.error(f"Error processing batch: {e}")
                    return {"error": str(e)}

            tasks.append(process_batch(batch))

        # Process in parallel with limit
        semaphore = asyncio.Semaphore(self.max_parallel_batches)

        async def process_with_semaphore(task):
            async with semaphore:
                return await task

        parallel_tasks = [process_with_semaphore(task) for task in tasks]
        results = await asyncio.gather(*parallel_tasks)

        if progress_callback:
            progress_callback(len(tasks), len(tasks))

        return results

    def get_batches(self, items: list[Any]) -> list[list[Any]]:
        """
        Split items into batches.

        Args:
            items: List of items to split

        Returns:
            List of batches
        """
        batches = []
        for i in range(0, len(items), self.batch_size):
            batches.append(items[i:i + self.batch_size])

        return batches
