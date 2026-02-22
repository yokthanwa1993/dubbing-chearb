import fs from 'fs';

let index = fs.readFileSync('src/index.ts', 'utf8');

// I need to add that D1 check for incoming telegram hooks!
// Searching for app.post('/api/telegram/:token'

index = index.replace(
"app.post('/api/telegram/:token', async (c) => {\n    const botId = c.get('botId')\n    const bucket = c.get('bucket')",
`app.post('/api/telegram/:token', async (c) => {
    const botId = c.get('botId')
    const bucket = c.get('bucket')
    
    // Check if the user is allowed
    const dataObj = await c.req.raw.clone().json().catch(() => null) as any;
    const chatId2 = dataObj?.message?.chat?.id;
    if (chatId2) {
        const allowed = await c.env.DB.prepare('SELECT 1 FROM allowed_users WHERE telegram_id = ?').bind(chatId2).first();
        if (!allowed) {
            console.log("Unauthorized telegram ID:", chatId2);
            return c.text('Unauthorized');
        }
    }
`
);

fs.writeFileSync('src/index.ts', index);
