-- =============================================================================
-- ADD THUMBNAIL SUPPORT TO DOCUMENTS TABLE
-- =============================================================================
-- Migration: 02_add_thumbnail_support
-- Description: Add columns to track server-generated thumbnails for images
-- Date: 2026-01-10
-- =============================================================================

-- Add thumbnail tracking columns to documents table
ALTER TABLE public.documents
ADD COLUMN IF NOT EXISTS thumbnail_key TEXT,
ADD COLUMN IF NOT EXISTS thumbnail_generated_at TIMESTAMPTZ,
ADD COLUMN IF NOT EXISTS image_width INTEGER,
ADD COLUMN IF NOT EXISTS image_height INTEGER;

-- Create index for efficient thumbnail lookups
CREATE INDEX IF NOT EXISTS idx_documents_thumbnail ON public.documents(thumbnail_key)
WHERE thumbnail_key IS NOT NULL;

-- Add comment for documentation
COMMENT ON COLUMN public.documents.thumbnail_key IS 'Storage key for generated thumbnail (256x256 JPEG) in thumbnails bucket';
COMMENT ON COLUMN public.documents.thumbnail_generated_at IS 'Timestamp when thumbnail was generated';
COMMENT ON COLUMN public.documents.image_width IS 'Original image width in pixels';
COMMENT ON COLUMN public.documents.image_height IS 'Original image height in pixels';
