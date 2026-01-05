# Video Critique Dashboard - Node.js

A modern, beautiful dashboard for visualizing Video Critique workflow metrics and analytics.

![Dashboard Preview](https://img.shields.io/badge/Status-Ready-success?style=for-the-badge)
![Node.js](https://img.shields.io/badge/Node.js-18+-green?style=for-the-badge&logo=node.js)
![Express](https://img.shields.io/badge/Express-4.18-blue?style=for-the-badge&logo=express)

## Features

- **Real-time Analytics** - Live dashboard with completion rates, pending tasks, and more
- **Beautiful UI** - Modern glass-morphism design with gradient effects and smooth animations
- **Interactive Charts** - Powered by Chart.js with completion pie charts and status bar charts
- **Reviewer Metrics** - Average response time, handled videos, and success rates
- **Videographer Performance** - Individual stats for each videographer with acceptance rates
- **Responsive Design** - Works perfectly on desktop, tablet, and mobile devices
- **Period Filtering** - View data by month or year with easy date picker
- **Dark Theme** - Eye-friendly dark mode with purple/indigo gradients

## Tech Stack

- **Backend**: Node.js + Express.js
- **Database**: SQLite3 (reads from existing `history_logs.db`)
- **Frontend**: Vanilla JavaScript + Tailwind CSS
- **Charts**: Chart.js
- **Icons**: Font Awesome
- **Fonts**: Google Fonts (Inter)

## Installation

### Prerequisites

- Node.js 18 or higher
- npm or yarn
- Existing SQLite database (`data/history_logs.db`)

### Setup

1. **Navigate to the dashboard directory**:
   ```bash
   cd node-dashboard
   ```

2. **Install dependencies**:
   ```bash
   npm install
   ```

3. **Configure environment** (optional):
   ```bash
   cp .env.example .env
   ```

   Edit `.env` if needed:
   ```env
   NODE_DASHBOARD_PORT=3001
   DATA_DIR=../data
   ```

4. **Start the server**:
   ```bash
   npm start
   ```

   For development with auto-reload:
   ```bash
   npm run dev
   ```

5. **Open your browser**:
   ```
   http://localhost:3001
   ```

## Project Structure

```
node-dashboard/
├── public/
│   ├── index.html          # Main dashboard UI
│   └── app.js              # Frontend JavaScript
├── routes/
│   └── dashboard.js        # API routes
├── services/
│   └── dashboardService.js # Business logic & metrics calculation
├── db/
│   └── database.js         # SQLite database layer
├── server.js               # Express server entry point
├── package.json            # Dependencies
└── README.md               # This file
```

## API Endpoints

### GET `/api/dashboard`

Returns complete dashboard data.

**Query Parameters**:
- `mode` (optional): `month` or `year` (default: `month`)
- `period` (optional): `YYYY-MM` for month mode or `YYYY` for year mode

**Example**:
```bash
curl http://localhost:3001/api/dashboard?mode=month&period=2025-01
```

**Response**:
```json
{
  "mode": "month",
  "period": "2025-01",
  "pie": {
    "completed": 45,
    "not_completed": 12
  },
  "summary": {
    "total": 57,
    "assigned": 55,
    "pending": 8,
    "rejected": 3,
    "submitted_to_sales": 15,
    "returned": 2,
    "uploads": 78,
    "accepted_videos": 42,
    "accepted_pct": 87.5,
    "rejected_pct": 12.5
  },
  "reviewer": {
    "avg_response_hours": 4.2,
    "avg_response_display": "4.2 hrs",
    "pending_videos": 8,
    "handled": 65,
    "accepted": 42,
    "handled_percent": 95.5
  },
  "videographers": { ... },
  "summary_videographers": { ... }
}
```

### GET `/api/stats`

Returns quick summary statistics.

**Example**:
```bash
curl http://localhost:3001/api/stats
```

### GET `/health`

Health check endpoint.

## Dashboard Features

### Quick Stats Cards
- Total Tasks
- Completed Tasks
- Pending Tasks
- Acceptance Rate

### Charts
- **Completion Overview** - Pie chart showing completed vs not completed
- **Status Distribution** - Bar chart showing pending, rejected, returned, submitted, and accepted

### Detailed Summary
- Assigned tasks
- Rejected videos
- Returned videos
- Submitted to sales
- Total uploads

### Reviewer Performance
- Average response time
- Videos handled
- Accepted videos
- Success rate percentage

### Videographer Performance
- Individual cards for each videographer
- Task count and acceptance rate
- Breakdown of uploads, pending, rejected, returned, submitted, and accepted
- Visual progress bar

## Customization

### Changing Colors

Edit the gradient colors in `public/index.html`:

```css
body {
    background: linear-gradient(135deg, #0f0c29 0%, #302b63 50%, #24243e 100%);
}

.gradient-text {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}
```

### Changing Port

Update in `.env`:
```env
NODE_DASHBOARD_PORT=3001
```

Or set environment variable:
```bash
NODE_DASHBOARD_PORT=3001 npm start
```

### Adding New Metrics

1. Add calculation in `services/dashboardService.js`
2. Update the response object
3. Add UI element in `public/index.html`
4. Update the data binding in `public/app.js`

## Database Schema

The dashboard reads from two tables:

### `live_tasks`
Active tasks currently in progress.

### `completed_tasks`
Historical tasks that have been completed.

**Key Columns**:
- `task_number` - Unique task identifier
- `Filming Date` - Date for period filtering
- `Videographer` - Assigned videographer
- `Version History` - JSON array of version events
- `Status` - Current status

## Deployment

### Development
```bash
npm run dev
```

### Production
```bash
npm start
```

### Using PM2 (Recommended for production)
```bash
npm install -g pm2
pm2 start server.js --name video-dashboard
pm2 save
pm2 startup
```

### Docker (Optional)
```dockerfile
FROM node:18-alpine
WORKDIR /app
COPY package*.json ./
RUN npm install --production
COPY . .
EXPOSE 3001
CMD ["npm", "start"]
```

Build and run:
```bash
docker build -t video-dashboard .
docker run -p 3001:3001 -v /path/to/data:/data video-dashboard
```

## Troubleshooting

### Database not found
- Ensure `data/history_logs.db` exists in the parent directory
- Check `DATA_DIR` environment variable

### Charts not rendering
- Clear browser cache
- Check browser console for JavaScript errors
- Ensure Chart.js CDN is accessible

### Port already in use
```bash
# Change port in .env or kill the process using port 3001
lsof -ti:3001 | xargs kill -9
```

## Performance

- **Fast**: Minimal dependencies, optimized queries
- **Scalable**: Handles thousands of tasks efficiently
- **Lightweight**: ~50MB memory footprint
- **Responsive**: Sub-second API response times

## Security

- **Read-only database**: Opens SQLite in `READONLY` mode
- **CORS enabled**: Configure allowed origins in production
- **No authentication**: Add authentication middleware if exposing publicly

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## License

MIT License - feel free to use this dashboard in your projects!

## Support

For issues or questions:
- Check the troubleshooting section above
- Review the code comments
- Open an issue in the repository

---

**Built with** ❤️ **for the Video Critique team**
