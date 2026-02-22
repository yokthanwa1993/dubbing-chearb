const fs = require('fs');
let code = fs.readFileSync('index.ts', 'utf8');

// replace the Env imports
code = code.replace(/import \{ Container \} from '@cloudflare\/containers'/, "import { Container } from '@cloudflare/containers'\nimport { BotBucket } from './utils/botBucket'\nimport { getBotId } from './utils/botAuth'");

// 1. replace all c.env.BUCKET with c.get('bucket') -> but we don't have that yet
// We will change:
// const app = new Hono<{ Bindings: Env }>()
// to:
// const app = new Hono<{ Bindings: Env, Variables: { botId: string; bucket: BotBucket } }>()

code = code.replace(
    'const app = new Hono<{ Bindings: Env }>()',
    'const app = new Hono<{ Bindings: Env, Variables: { botId: string; bucket: BotBucket } }>()'
);

// 2. Add middleware after CORS
const mw = `
app.use('*', async (c, next) => {
    let token = c.req.header('x-auth-token') || '';
    if (!token && c.req.path.startsWith('/api/telegram/')) {
        const parts = c.req.path.split('/');
        // /api/telegram/:token -> size 4 -> parts[3]
        if (parts.length >= 4) token = parts[3];
    }
    const botId = getBotId(token);
    c.set('botId', botId);
    c.set('bucket', new BotBucket(c.env.BUCKET, botId));
    await next();
})
`;

code = code.replace('// Health check', mw + '\n// Health check');

// replace c.env.BUCKET with c.get('bucket') globally
code = code.replace(/c\.env\.BUCKET/g, "c.get('bucket')");

// Fix /api/telegram
code = code.replace("app.post('/api/telegram', async (c) => {", "app.post('/api/telegram/:token', async (c) => {\n    const botId = c.get('botId')\n    const bucket = c.get('bucket')");

code = code.replace(/c\.env\.TELEGRAM_BOT_TOKEN/g, "c.req.param('token') || c.req.header('x-auth-token') || c.env.TELEGRAM_BOT_TOKEN");
// wait! there are some places where it might just use c.env.TELEGRAM_BOT_TOKEN but we are extracting it dynamically. For Telegram webhook, the token is `c.req.param('token')`. For other APIs it's from headers.

// For runPipeline, processNextInQueue, we need to pass botId and botBucket
// runPipeline(c.env, videoUrl, chatId, 0, videoId) => runPipeline(c.env, videoUrl, chatId, 0, videoId, botId)
code = code.replace(/runPipeline\(c\.env, videoUrl, chatId, 0, videoId\)/g, "runPipeline(c.env, videoUrl, chatId, 0, videoId, botId)");

// processNextInQueue(c.env) => processNextInQueue(c.env, bucket, c.get('botId'))
// let's isolate processNextInQueue replacements
code = code.replace(/processNextInQueue\(c\.env\)/g, "processNextInQueue(c.env, c.get('bucket'), c.get('botId'))");
// If there is botBucket/botId missing in scope, we will declare `const botId = c.get('botId'); const bucket = c.get('bucket');` where needed.

// Fix DB queries adding bot_id
// INSERT INTO pages (id, name, image_url, access_token, post_interval_minutes) VALUES (?, ?, ?, ?, ?)
code = code.replace(
    "'INSERT INTO pages (id, name, image_url, access_token, post_interval_minutes) VALUES (?, ?, ?, ?, ?)'\n        ).bind(id, name, image_url, access_token, post_interval_minutes)",
    "'INSERT INTO pages (id, name, image_url, access_token, post_interval_minutes, bot_id) VALUES (?, ?, ?, ?, ?, ?)'\n        ).bind(id, name, image_url, access_token, post_interval_minutes, c.get('botId'))"
);

// INSERT INTO pages (id, name, image_url, access_token, post_interval_minutes, is_active) VALUES (?, ?, ?, ?, 60, 1)
code = code.replace(
    "'INSERT INTO pages (id, name, image_url, access_token, post_interval_minutes, is_active) VALUES (?, ?, ?, ?, 60, 1)'\n                ).bind(pageId, pageName, pageImageUrl, pageAccessToken)",
    "'INSERT INTO pages (id, name, image_url, access_token, post_interval_minutes, is_active, bot_id) VALUES (?, ?, ?, ?, 60, 1, ?)'\n                ).bind(pageId, pageName, pageImageUrl, pageAccessToken, c.get('botId'))"
);

// SELECT id, name, ... FROM pages ORDER BY created_at DESC -> WHERE bot_id = ?
code = code.replace(
    "'SELECT id, name, image_url, access_token, comment_token, post_interval_minutes, post_hours, is_active, last_post_at, created_at FROM pages ORDER BY created_at DESC'\n        ).all()",
    "'SELECT id, name, image_url, access_token, comment_token, post_interval_minutes, post_hours, is_active, last_post_at, created_at FROM pages WHERE bot_id = ? ORDER BY created_at DESC'\n        ).bind(c.get('botId')).all()"
);

// SELECT ph.*, p.name as page_name ... FROM post_history ph JOIN pages p ON ... WHERE ph.status != 'deleted'
code = code.replace(
    "WHERE ph.status != 'deleted'\n             ORDER BY ph.posted_at DESC LIMIT 100`\n        ).all()",
    "WHERE ph.status != 'deleted' AND p.bot_id = ?\n             ORDER BY ph.posted_at DESC LIMIT 100`\n        ).bind(c.get('botId')).all()"
);

// INSERT INTO post_queue (video_id, page_id, scheduled_at)
code = code.replace(
    "'INSERT INTO post_queue (video_id, page_id, scheduled_at) VALUES (?, ?, ?)'\n        ).bind(video_id, pageId, scheduled_at)",
    "'INSERT INTO post_queue (video_id, page_id, scheduled_at, bot_id) VALUES (?, ?, ?, ?)'\n        ).bind(video_id, pageId, scheduled_at, c.get('botId'))"
);

// INSERT INTO post_history (page_id, video_id, posted_at, status) VALUES (?, ?, ?, ?) -> add bot_id
code = code.replace(
    "'INSERT INTO post_history (page_id, video_id, posted_at, status) VALUES (?, ?, ?, ?)'\n        ).bind(page.id, unpostedId, nowStr, 'posting')",
    "'INSERT INTO post_history (page_id, video_id, posted_at, status, bot_id) VALUES (?, ?, ?, ?, ?)'\n        ).bind(page.id, unpostedId, nowStr, 'posting', c.get('botId'))"
);
code = code.replace(
    "'INSERT INTO post_history (page_id, video_id, posted_at, status) VALUES (?, ?, ?, ?)'\n        ).bind(page.id, unpostedId, nowISO, 'posting')",
    "'INSERT INTO post_history (page_id, video_id, posted_at, status, bot_id) VALUES (?, ?, ?, ?, ?)'\n        ).bind(page.id, unpostedId, nowISO, 'posting', c.get('botId') || 'cron')"
); // Note: in cron, we will need to inject botId into this correctly! We'll fix it manualiy.

fs.writeFileSync('index.ts', code);
console.log('index updated automatically');
