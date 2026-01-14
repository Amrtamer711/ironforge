#!/usr/bin/env npx ts-node
/**
 * =============================================================================
 * Supabase Full Sync Script
 * =============================================================================
 * Syncs EVERYTHING between Supabase projects:
 * - Database (schema + data)
 * - Storage buckets
 * - Storage files
 * - Edge functions
 *
 * Usage:
 *   npx ts-node scripts/sync-supabase.ts --direction dev-to-prod --all
 *   npx ts-node scripts/sync-supabase.ts --direction prod-to-dev --db --storage
 *   npx ts-node scripts/sync-supabase.ts --direction dev-to-prod --project salesbot --db
 *
 * Flags:
 *   --direction     dev-to-prod | prod-to-dev (required)
 *   --project       all | ui | salesbot | assetmgmt | videocritique (default: all)
 *   --all           Sync everything (db + storage + edge functions)
 *   --db            Sync database only
 *   --storage       Sync storage buckets and files
 *   --edge          Sync edge functions
 *   --dry-run       Show what would be done without doing it
 *
 * Requirements:
 *   - PostgreSQL 17+ (brew install postgresql@17)
 *   - Node.js 18+
 *   - Supabase CLI (brew install supabase/tap/supabase)
 * =============================================================================
 */

import { createClient, SupabaseClient } from '@supabase/supabase-js';
import { execSync } from 'child_process';
import * as fs from 'fs';
import * as path from 'path';
import * as dotenv from 'dotenv';
import * as tus from 'tus-js-client';

// Load environment variables from project root
const projectRoot = process.cwd();
const envPath = path.join(projectRoot, '.env');
dotenv.config({ path: envPath });

// =============================================================================
// Configuration
// =============================================================================

interface ProjectConfig {
  name: string;
  devUrl: string;
  devServiceKey: string;
  devDbUri: string;
  prodUrl: string;
  prodServiceKey: string;
  prodDbUri: string;
  schemas: string[]; // Base schemas (will be auto-discovered if syncAllSchemas is true)
  dataTables: string[]; // Tables to sync from public schema only
  syncAllSchemas: boolean; // If true, discover and sync ALL schemas + ALL data
  storageBuckets: string[];
  edgeFunctions: string[];
}

const PROJECTS: Record<string, ProjectConfig> = {
  ui: {
    name: 'UI',
    devUrl: process.env.UI_DEV_SUPABASE_URL!,
    devServiceKey: process.env.UI_DEV_SUPABASE_SERVICE_ROLE_KEY!,
    devDbUri: process.env.UI_DEV_DB_URI!,
    prodUrl: process.env.UI_PROD_SUPABASE_URL!,
    prodServiceKey: process.env.UI_PROD_SUPABASE_SERVICE_ROLE_KEY!,
    prodDbUri: process.env.UI_PROD_DB_URI!,
    schemas: ['public'],
    dataTables: [
      'profiles',
      'permissions',
      'permission_sets',
      'permission_set_permissions',
      'companies',
      'teams',
      'modules',
    ],
    syncAllSchemas: true,
    storageBuckets: [],
    edgeFunctions: [],
  },
  salesbot: {
    name: 'Salesbot',
    devUrl: process.env.SALESBOT_DEV_SUPABASE_URL!,
    devServiceKey: process.env.SALESBOT_DEV_SUPABASE_SERVICE_ROLE_KEY!,
    devDbUri: process.env.SALESBOT_DEV_DB_URI!,
    prodUrl: process.env.SALESBOT_PROD_SUPABASE_URL!,
    prodServiceKey: process.env.SALESBOT_PROD_SUPABASE_SERVICE_ROLE_KEY!,
    prodDbUri: process.env.SALESBOT_PROD_DB_URI!,
    schemas: [
      'public',
      'backlite_dubai',
      'backlite_uk',
      'backlite_ksa',
      'multiply_uae',
      'viola_outdoor',
      'viola_communications',
    ],
    dataTables: ['companies', 'locations', 'rate_cards', 'mockup_frames'],
    syncAllSchemas: true,
    storageBuckets: ['proposals', 'uploads', 'fonts', 'booking_orders', 'thumbnails', 'static'],
    edgeFunctions: [],
  },
  assetmgmt: {
    name: 'Asset Management',
    devUrl: process.env.ASSETMGMT_DEV_SUPABASE_URL!,
    devServiceKey: process.env.ASSETMGMT_DEV_SUPABASE_SERVICE_ROLE_KEY!,
    devDbUri: process.env.ASSETMGMT_DEV_DB_URI!,
    prodUrl: process.env.ASSETMGMT_PROD_SUPABASE_URL!,
    prodServiceKey: process.env.ASSETMGMT_PROD_SUPABASE_SERVICE_ROLE_KEY!,
    prodDbUri: process.env.ASSETMGMT_PROD_DB_URI!,
    schemas: ['public'],
    dataTables: ['companies'],
    syncAllSchemas: true,
    storageBuckets: ['templates', 'assets', 'mockups'],
    edgeFunctions: ['rename-storage-file', 'move-storage-file'],
  },
  videocritique: {
    name: 'Video Critique',
    devUrl: process.env.VIDEOCRITIQUE_DEV_SUPABASE_URL!,
    devServiceKey: process.env.VIDEOCRITIQUE_DEV_SUPABASE_SERVICE_ROLE_KEY!,
    devDbUri: process.env.VIDEOCRITIQUE_DEV_DB_URI!,
    prodUrl: process.env.VIDEOCRITIQUE_PROD_SUPABASE_URL!,
    prodServiceKey: process.env.VIDEOCRITIQUE_PROD_SUPABASE_SERVICE_ROLE_KEY!,
    prodDbUri: process.env.VIDEOCRITIQUE_PROD_DB_URI!,
    schemas: ['public'],
    dataTables: [],
    syncAllSchemas: true,
    storageBuckets: [],
    edgeFunctions: [],
  },
};

const DUMP_DIR = path.join(process.env.HOME!, 'supabase_migration');
const PG_PATH = '/opt/homebrew/opt/postgresql@17/bin';
const LARGE_FILE_THRESHOLD = 50 * 1024 * 1024; // 50MB - files larger than this use TUS

// =============================================================================
// Utility Functions
// =============================================================================

const colors = {
  reset: '\x1b[0m',
  red: '\x1b[31m',
  green: '\x1b[32m',
  yellow: '\x1b[33m',
  blue: '\x1b[34m',
  cyan: '\x1b[36m',
};

function log(message: string, color: keyof typeof colors = 'reset') {
  console.log(`${colors[color]}${message}${colors.reset}`);
}

function logInfo(message: string) {
  log(`[INFO] ${message}`, 'blue');
}

function logSuccess(message: string) {
  log(`[SUCCESS] ${message}`, 'green');
}

function logWarn(message: string) {
  log(`[WARN] ${message}`, 'yellow');
}

function logError(message: string) {
  log(`[ERROR] ${message}`, 'red');
}

function exec(command: string, options: { silent?: boolean } = {}): string {
  try {
    const result = execSync(command, {
      encoding: 'utf-8',
      env: { ...process.env, PATH: `${PG_PATH}:${process.env.PATH}` },
      stdio: options.silent ? 'pipe' : 'inherit',
    });
    return result?.toString() || '';
  } catch (error: any) {
    if (!options.silent) {
      logError(`Command failed: ${command}`);
    }
    throw error;
  }
}

function ensureDumpDir() {
  if (!fs.existsSync(DUMP_DIR)) {
    fs.mkdirSync(DUMP_DIR, { recursive: true });
  }
}

// =============================================================================
// TUS Resumable Upload (for large files >50MB)
// =============================================================================

async function uploadWithTus(
  targetUrl: string,
  targetKey: string,
  bucketName: string,
  filePath: string,
  fileBlob: Blob
): Promise<void> {
  // Convert Blob to Buffer for Node.js compatibility
  const arrayBuffer = await fileBlob.arrayBuffer();
  const buffer = Buffer.from(arrayBuffer);

  return new Promise((resolve, reject) => {
    const upload = new tus.Upload(buffer, {
      endpoint: `${targetUrl}/storage/v1/upload/resumable`,
      retryDelays: [0, 3000, 5000, 10000, 20000],
      headers: {
        apikey: targetKey,
        authorization: `Bearer ${targetKey}`,
        'x-upsert': 'true',
      },
      uploadDataDuringCreation: true,
      removeFingerprintOnSuccess: true,
      metadata: {
        bucketName: bucketName,
        objectName: filePath,
        contentType: 'application/octet-stream',
      },
      chunkSize: 6 * 1024 * 1024, // 6MB chunks
      onError: (error) => {
        reject(error);
      },
      onProgress: (bytesUploaded, bytesTotal) => {
        const pct = ((bytesUploaded / bytesTotal) * 100).toFixed(0);
        process.stdout.write(`\r        Progress: ${pct}%`);
      },
      onSuccess: () => {
        process.stdout.write('\r        Progress: 100% - Done\n');
        resolve();
      },
    });

    upload.start();
  });
}

// =============================================================================
// Database Sync
// =============================================================================

// System schemas to exclude from discovery
const EXCLUDED_SCHEMAS = [
  'pg_catalog',
  'pg_toast',
  'information_schema',
  'auth',
  'storage',
  'graphql',
  'graphql_public',
  'realtime',
  'supabase_functions',
  'supabase_migrations',
  'extensions',
  'vault',
  'pgsodium',
  'pgsodium_masks',
  '_realtime',
  'net',
  'cron',
];

function discoverSchemas(dbUri: string): string[] {
  try {
    const result = exec(
      `psql "${dbUri}" -t -c "SELECT schema_name FROM information_schema.schemata WHERE schema_name NOT LIKE 'pg_%' ORDER BY schema_name;"`,
      { silent: true }
    );
    const schemas = result
      .split('\n')
      .map((s) => s.trim())
      .filter((s) => s && !EXCLUDED_SCHEMAS.includes(s));
    return schemas;
  } catch {
    return ['public'];
  }
}

async function syncDatabase(
  project: ProjectConfig,
  sourceDbUri: string,
  targetDbUri: string,
  direction: string,
  dryRun: boolean
): Promise<void> {
  logInfo(`Syncing ${project.name} database (${direction})...`);

  // Discover all schemas from source
  logInfo(`  Discovering schemas...`);
  const schemas = project.syncAllSchemas ? discoverSchemas(sourceDbUri) : project.schemas;
  logInfo(`  Found schemas: ${schemas.join(', ')}`);

  if (dryRun) {
    logWarn(`  [DRY RUN] Would dump schemas: ${schemas.join(', ')}`);
    logWarn(`  [DRY RUN] Would dump ALL data from ALL schemas`);
    logWarn(`  [DRY RUN] Would nuke target and restore`);
    return;
  }

  ensureDumpDir();
  const schemaFile = path.join(DUMP_DIR, `${project.name.toLowerCase()}_schema.sql`);
  const dataFile = path.join(DUMP_DIR, `${project.name.toLowerCase()}_data.sql`);

  // Dump schema structure for ALL discovered schemas
  logInfo(`  Dumping schema structure...`);
  const schemaArgs = schemas.map((s) => `--schema=${s}`).join(' ');
  try {
    exec(
      `pg_dump "${sourceDbUri}" ${schemaArgs} --schema-only --no-owner --no-privileges > "${schemaFile}"`,
      { silent: true }
    );
  } catch {
    // Fallback to just public schema
    exec(`pg_dump "${sourceDbUri}" --schema=public --schema-only --no-owner --no-privileges > "${schemaFile}"`, {
      silent: true,
    });
  }

  // Dump ALL data from ALL schemas
  logInfo(`  Dumping data from all schemas...`);
  try {
    exec(
      `pg_dump "${sourceDbUri}" ${schemaArgs} --data-only > "${dataFile}" 2>/dev/null`,
      { silent: true }
    );
  } catch {
    // Ignore errors for missing tables
    logWarn(`  Warning: Some data export errors (may be normal)`);
  }

  // Nuke target - drop ALL discovered schemas
  logInfo(`  Nuking target schemas...`);
  const dropSchemas = schemas.map((s) => `DROP SCHEMA IF EXISTS ${s} CASCADE;`).join(' ');
  exec(
    `psql "${targetDbUri}" -c "${dropSchemas} CREATE SCHEMA public; GRANT ALL ON SCHEMA public TO postgres, anon, authenticated, service_role;"`,
    { silent: true }
  );

  // Restore schema structure
  logInfo(`  Restoring schema structure...`);
  try {
    exec(`psql "${targetDbUri}" < "${schemaFile}"`, { silent: true });
  } catch {
    // Ignore permission errors
  }

  // Restore data
  if (fs.existsSync(dataFile) && fs.statSync(dataFile).size > 0) {
    logInfo(`  Restoring data...`);
    try {
      exec(`psql "${targetDbUri}" < "${dataFile}"`, { silent: true });
    } catch {
      // Ignore errors
    }
  }

  // Grant permissions to Supabase roles for all schemas
  logInfo(`  Granting permissions to Supabase roles...`);
  let grantErrors = 0;
  for (const schema of schemas) {
    try {
      // Use DO block for atomic permission granting
      exec(
        `psql "${targetDbUri}" -c "
          DO \\$\\$
          BEGIN
            -- Schema usage
            GRANT USAGE ON SCHEMA ${schema} TO anon, authenticated, service_role;

            -- Existing objects
            GRANT ALL ON ALL TABLES IN SCHEMA ${schema} TO anon, authenticated, service_role;
            GRANT ALL ON ALL SEQUENCES IN SCHEMA ${schema} TO anon, authenticated, service_role;
            GRANT ALL ON ALL FUNCTIONS IN SCHEMA ${schema} TO anon, authenticated, service_role;

            -- Default privileges for future objects
            ALTER DEFAULT PRIVILEGES IN SCHEMA ${schema} GRANT ALL ON TABLES TO anon, authenticated, service_role;
            ALTER DEFAULT PRIVILEGES IN SCHEMA ${schema} GRANT ALL ON SEQUENCES TO anon, authenticated, service_role;
            ALTER DEFAULT PRIVILEGES IN SCHEMA ${schema} GRANT ALL ON FUNCTIONS TO anon, authenticated, service_role;

            RAISE NOTICE 'Granted permissions on schema: ${schema}';
          EXCEPTION WHEN OTHERS THEN
            RAISE WARNING 'Error granting permissions on ${schema}: %', SQLERRM;
          END
          \\$\\$;
        "`,
        { silent: true }
      );
    } catch (e) {
      grantErrors++;
      logWarn(`  Warning: Failed to grant permissions on schema ${schema}`);
    }
  }

  // Verify permissions were applied
  logInfo(`  Verifying permissions...`);
  try {
    const verifyResult = exec(
      `psql "${targetDbUri}" -t -c "
        SELECT COUNT(*) FROM information_schema.table_privileges
        WHERE grantee = 'service_role' AND table_schema IN (${schemas.map((s) => `'${s}'`).join(',')});
      "`,
      { silent: true }
    );
    const grantCount = parseInt(verifyResult.trim(), 10);
    if (grantCount > 0) {
      logSuccess(`  Verified: service_role has ${grantCount} table privileges`);
    } else {
      logWarn(`  Warning: service_role has no table privileges - check for errors`);
    }
  } catch {
    logWarn(`  Warning: Could not verify permissions`);
  }

  if (grantErrors > 0) {
    logWarn(`  ${grantErrors} schema(s) had grant errors`);
  }

  logSuccess(`  ${project.name} database synced (${schemas.length} schemas)`);
}

// =============================================================================
// Storage Sync
// =============================================================================

async function listAllFiles(
  client: SupabaseClient,
  bucketName: string,
  prefix: string = ''
): Promise<string[]> {
  const allFiles: string[] = [];

  const { data: items, error } = await client.storage.from(bucketName).list(prefix, {
    limit: 1000,
  });

  if (error || !items) {
    return allFiles;
  }

  for (const item of items) {
    const itemPath = prefix ? `${prefix}/${item.name}` : item.name;

    if (item.id === null) {
      // It's a folder - recurse into it
      const nestedFiles = await listAllFiles(client, bucketName, itemPath);
      allFiles.push(...nestedFiles);
    } else {
      // It's a file
      allFiles.push(itemPath);
    }
  }

  return allFiles;
}

async function syncStorage(
  project: ProjectConfig,
  sourceClient: SupabaseClient,
  targetClient: SupabaseClient,
  targetUrl: string,
  targetKey: string,
  direction: string,
  dryRun: boolean
): Promise<void> {
  if (project.storageBuckets.length === 0) {
    logInfo(`  No storage buckets for ${project.name}`);
    return;
  }

  logInfo(`Syncing ${project.name} storage (${direction})...`);

  for (const bucketName of project.storageBuckets) {
    logInfo(`  Bucket: ${bucketName}`);

    // List all files recursively from source
    const allFiles = await listAllFiles(sourceClient, bucketName);
    logInfo(`    Found ${allFiles.length} files in source`);

    if (dryRun) {
      logWarn(`    [DRY RUN] Would create bucket if not exists`);
      logWarn(`    [DRY RUN] Would copy ${allFiles.length} files`);
      for (const f of allFiles.slice(0, 5)) {
        logWarn(`      - ${f}`);
      }
      if (allFiles.length > 5) {
        logWarn(`      ... and ${allFiles.length - 5} more`);
      }
      continue;
    }

    // Create bucket in target if not exists
    try {
      const { error: createError } = await targetClient.storage.createBucket(bucketName, {
        public: false,
      });
      if (createError && !createError.message.includes('already exists')) {
        logWarn(`    Could not create bucket: ${createError.message}`);
      }
    } catch (e) {
      // Bucket might already exist
    }

    if (allFiles.length === 0) {
      logInfo(`    No files to copy`);
      continue;
    }

    // Copy files
    let copied = 0;
    let failed = 0;
    const total = allFiles.length;

    for (let i = 0; i < allFiles.length; i++) {
      const filePath = allFiles[i];
      const fileNum = i + 1;

      try {
        // Show progress for all files (clear line first with ANSI escape)
        const shortName = filePath.split('/').pop() || filePath;
        process.stdout.write(`\r\x1b[K      [${fileNum}/${total}] ${shortName.substring(0, 40)}`);

        // Download from source
        const { data: fileData, error: downloadError } = await sourceClient.storage
          .from(bucketName)
          .download(filePath);

        if (downloadError || !fileData) {
          console.log(''); // newline
          logWarn(`      Failed to download: ${filePath}`);
          failed++;
          continue;
        }

        const fileSize = fileData.size;

        if (fileSize > LARGE_FILE_THRESHOLD) {
          // Use TUS resumable upload for large files (>50MB)
          console.log(''); // newline before TUS progress
          logInfo(`      Large file (${Math.round(fileSize / 1024 / 1024)}MB): ${filePath}`);
          try {
            await uploadWithTus(targetUrl, targetKey, bucketName, filePath, fileData);
            copied++;
          } catch (e: any) {
            logWarn(`      TUS upload failed: ${filePath} - ${e.message}`);
            failed++;
          }
        } else {
          // Standard upload for smaller files
          const { error: uploadError } = await targetClient.storage
            .from(bucketName)
            .upload(filePath, fileData, { upsert: true });

          if (uploadError) {
            console.log(''); // newline
            logWarn(`      Failed to upload: ${filePath} - ${uploadError.message}`);
            failed++;
          } else {
            copied++;
          }
        }
      } catch (e: any) {
        console.log(''); // newline
        logWarn(`      Error copying ${filePath}: ${e.message}`);
        failed++;
      }
    }

    console.log(''); // clear the progress line
    logSuccess(`    Copied ${copied} files${failed > 0 ? `, ${failed} failed` : ''}`);
  }
}

// =============================================================================
// Edge Functions Sync
// =============================================================================
// Note: Edge functions require Supabase CLI or MCP tools to deploy.
// The Management API has limited access for function content.
// Use: supabase functions deploy <function-name> --project-ref <ref>
// Or use MCP: mcp__supabase-<project>-prod__deploy_edge_function

async function syncEdgeFunctions(
  project: ProjectConfig,
  sourceProjectRef: string,
  targetProjectRef: string,
  direction: string,
  dryRun: boolean
): Promise<void> {
  if (project.edgeFunctions.length === 0) {
    return;
  }

  logInfo(`Syncing ${project.name} edge functions (${direction})...`);
  logWarn(`  Edge functions must be deployed via Supabase CLI or MCP tools.`);
  logInfo(`  Functions to deploy to ${targetProjectRef}:`);

  for (const funcName of project.edgeFunctions) {
    logInfo(`    - ${funcName}`);
  }

  logInfo(`\n  Deploy commands:`);
  for (const funcName of project.edgeFunctions) {
    console.log(`    supabase functions deploy ${funcName} --project-ref ${targetProjectRef}`);
  }
  console.log('');
}

// =============================================================================
// Main
// =============================================================================

async function main() {
  const args = process.argv.slice(2);

  // Parse arguments
  const getArg = (name: string): string | undefined => {
    const index = args.indexOf(`--${name}`);
    if (index !== -1 && args[index + 1] && !args[index + 1].startsWith('--')) {
      return args[index + 1];
    }
    return undefined;
  };

  const hasFlag = (name: string): boolean => args.includes(`--${name}`);

  const direction = getArg('direction');
  const projectFilter = getArg('project') || 'all';
  const syncAll = hasFlag('all');
  const syncDb = hasFlag('db') || syncAll;
  const syncStorageFlag = hasFlag('storage') || syncAll;
  const syncEdge = hasFlag('edge') || syncAll;
  const dryRun = hasFlag('dry-run');

  // Validate
  if (!direction || !['dev-to-prod', 'prod-to-dev'].includes(direction)) {
    console.log(`
Usage: npx ts-node scripts/sync-supabase.ts --direction <dev-to-prod|prod-to-dev> [options]

Options:
  --direction     dev-to-prod | prod-to-dev (required)
  --project       all | ui | salesbot | assetmgmt | videocritique (default: all)
  --all           Sync everything (db + storage + edge functions)
  --db            Sync database only
  --storage       Sync storage buckets and files
  --edge          Sync edge functions
  --dry-run       Show what would be done without doing it

Examples:
  npx ts-node scripts/sync-supabase.ts --direction dev-to-prod --all
  npx ts-node scripts/sync-supabase.ts --direction prod-to-dev --db --storage
  npx ts-node scripts/sync-supabase.ts --direction dev-to-prod --project salesbot --db
    `);
    process.exit(1);
  }

  if (!syncDb && !syncStorageFlag && !syncEdge) {
    logError('No sync flags specified. Use --all, --db, --storage, or --edge');
    process.exit(1);
  }

  // Header
  console.log(`
==============================================
  Supabase Full Sync
==============================================
  Direction: ${direction}
  Project:   ${projectFilter}
  Database:  ${syncDb ? 'YES' : 'NO'}
  Storage:   ${syncStorageFlag ? 'YES' : 'NO'}
  Edge:      ${syncEdge ? 'YES' : 'NO'}
  Dry Run:   ${dryRun ? 'YES' : 'NO'}
==============================================
`);

  // Get projects to sync
  const projectsToSync =
    projectFilter === 'all' ? Object.keys(PROJECTS) : [projectFilter];

  for (const projectKey of projectsToSync) {
    const project = PROJECTS[projectKey];
    if (!project) {
      logError(`Unknown project: ${projectKey}`);
      continue;
    }

    console.log(`\n--- ${project.name} ---\n`);

    // Determine source and target
    const isDevToProd = direction === 'dev-to-prod';
    const sourceDbUri = isDevToProd ? project.devDbUri : project.prodDbUri;
    const targetDbUri = isDevToProd ? project.prodDbUri : project.devDbUri;
    const sourceUrl = isDevToProd ? project.devUrl : project.prodUrl;
    const targetUrl = isDevToProd ? project.prodUrl : project.devUrl;
    const sourceKey = isDevToProd ? project.devServiceKey : project.prodServiceKey;
    const targetKey = isDevToProd ? project.prodServiceKey : project.devServiceKey;

    // Get project refs from URLs
    const sourceProjectRef = sourceUrl.replace('https://', '').replace('.supabase.co', '');
    const targetProjectRef = targetUrl.replace('https://', '').replace('.supabase.co', '');

    // Sync database
    if (syncDb) {
      await syncDatabase(project, sourceDbUri, targetDbUri, direction, dryRun);
    }

    // Sync storage
    if (syncStorageFlag && project.storageBuckets.length > 0) {
      const sourceClient = createClient(sourceUrl, sourceKey);
      const targetClient = createClient(targetUrl, targetKey);
      await syncStorage(project, sourceClient, targetClient, targetUrl, targetKey, direction, dryRun);
    }

    // Sync edge functions
    if (syncEdge && project.edgeFunctions.length > 0) {
      await syncEdgeFunctions(project, sourceProjectRef, targetProjectRef, direction, dryRun);
    }
  }

  console.log(`\n==============================================`);
  logSuccess('Sync complete!');
  console.log(`==============================================\n`);
}

main().catch((error) => {
  logError(error.message);
  process.exit(1);
});
