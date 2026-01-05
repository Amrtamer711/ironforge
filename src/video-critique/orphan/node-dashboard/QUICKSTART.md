# Quick Start Guide

Get your Video Critique Dashboard up and running in 3 minutes!

## Installation

```bash
# 1. Navigate to the dashboard directory
cd node-dashboard

# 2. Install dependencies
npm install

# 3. Start the server
npm start
```

## Access the Dashboard

Open your browser and go to:
```
http://localhost:3001
```

That's it! The dashboard will automatically connect to your existing database at `../data/history_logs.db`.

## Features at a Glance

- **Filter by Period**: Use the dropdown to switch between monthly and yearly views
- **Interactive Charts**: Hover over charts for detailed information
- **Real-time Data**: Click "Refresh" to update with latest data
- **Responsive Design**: Works on all devices

## Common Tasks

### Change the Port

Create a `.env` file:
```env
NODE_DASHBOARD_PORT=3001
```

### Development Mode (Auto-reload)

```bash
npm run dev
```

### View API Data Directly

```bash
curl http://localhost:3001/api/dashboard
```

## Next Steps

- Read the full [README.md](README.md) for detailed documentation
- Customize the colors and styling in `public/index.html`
- Add your own metrics in `services/dashboardService.js`

## Troubleshooting

**Database not found?**
- Ensure you have `data/history_logs.db` in the parent directory

**Port already in use?**
- Change the port in `.env` or kill the process: `lsof -ti:3001 | xargs kill -9`

**Charts not loading?**
- Check your internet connection (CDN dependencies)
- Clear browser cache

---

**Enjoy your beautiful new dashboard!** 🚀
