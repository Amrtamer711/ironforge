# Mockup Studio

A beautiful, modern platform for setting up billboard mockup frames with advanced features.

## Features

### 🎨 Modern Beautiful Design
- Sleek gradient UI with smooth animations
- Responsive design that works on all devices
- Professional card-based layout
- Toast notifications for user feedback

### 🔍 Native Zoom & Pixel Upscaling
- **Native Zoom Controls**: Zoom in/out with buttons or mouse wheel
- **Pixel Upscaling**: Toggle pixel-perfect rendering for clearer frame setup
- **Fit to Screen**: Automatically fit the image to your viewport
- **Pan Support**: Hold Shift + Click or use middle mouse button to pan around

### ✏️ Advanced Frame Editor
- Click and drag to define frame areas
- Visual feedback with colored overlays
- Live progress tracking
- Adjustable edge blur per frame
- Undo functionality

### 🔄 Edit Mode
- Edit existing templates frame by frame
- Navigate through frames sequentially
- Replace individual frames without starting over
- Visual overlay shows current frame being edited

### 💾 Template Management
- Save templates with location metadata
- View all templates in a beautiful grid
- Delete unwanted templates
- Templates stored with full frame data

## Installation

1. **Install Dependencies**
   ```bash
   cd mockup-studio
   npm install
   ```

2. **Start the Server**
   ```bash
   npm start
   ```

   Or for development with auto-reload:
   ```bash
   npm run dev
   ```

3. **Open in Browser**
   ```
   http://localhost:3001
   ```

## Usage

### Creating a New Template

1. Click **"Create New"** mode
2. Drag and drop or click to upload a billboard image
3. Select the location from the dropdown
4. **Define Frames**:
   - Click and drag on the canvas to draw a frame
   - Use zoom controls to get precise positioning
   - Enable **Pixel Upscale** for even clearer frame definition
   - Adjust edge blur if needed
   - Click "Next Frame" to move to the next frame
   - Repeat until all frames are defined
5. Click **"Finish & Save"** when done

### Editing an Existing Template

1. Click **"Edit Template"** mode
2. Select a template from the list
3. The first frame will be shown with an overlay
4. Click and drag to redefine the frame area
5. Click **"Next Frame"** to move to the next frame
6. Continue through all frames
7. Click **"Finish & Save"** to update the template

### Zoom Controls

- **Zoom In** (+): Increase zoom level
- **Zoom Out** (-): Decrease zoom level
- **Fit to Screen**: Reset zoom to fit entire image
- **Pixel Upscale**: Toggle crisp pixel rendering for precise frame setup
- **Mouse Wheel**: Scroll to zoom in/out
- **Shift + Click**: Pan around the image

### Keyboard Shortcuts

- **Mouse Wheel**: Zoom in/out
- **Shift + Drag**: Pan the canvas
- **Middle Mouse + Drag**: Pan the canvas

## API Endpoints

### Upload Image
```
POST /api/upload
Content-Type: multipart/form-data

Response: { success: true, imageUrl: string, filename: string }
```

### Get All Templates
```
GET /api/templates

Response: Template[]
```

### Get Single Template
```
GET /api/templates/:locationKey

Response: Template
```

### Save Template
```
POST /api/templates
Content-Type: application/json

Body: {
  locationKey: string,
  frames: Frame[],
  imageUrl: string,
  metadata: object
}

Response: { success: true, template: Template }
```

### Delete Template
```
DELETE /api/templates/:locationKey

Response: { success: true }
```

## Data Structure

### Template
```javascript
{
  locationKey: string,
  frames: [
    {
      points: [[x, y], [x, y], [x, y], [x, y]], // 4 corners
      config: {
        blurStrength: number
      }
    }
  ],
  imageUrl: string,
  metadata: {
    imageWidth: number,
    imageHeight: number,
    totalFrames: number
  },
  createdAt: ISO8601,
  updatedAt: ISO8601
}
```

## Technology Stack

- **Backend**: Node.js + Express
- **File Uploads**: Multer
- **Frontend**: Vanilla JavaScript (ES6+)
- **Styling**: Modern CSS with custom properties
- **Canvas**: HTML5 Canvas API for image manipulation

## Directory Structure

```
mockup-studio/
├── server.js              # Express server
├── package.json           # Dependencies
├── data/                  # JSON data storage
│   └── templates.json     # Template database
├── uploads/               # Uploaded images
└── public/                # Frontend assets
    ├── index.html         # Main HTML
    ├── css/
    │   └── styles.css     # Beautiful modern styles
    └── js/
        └── app.js         # Application logic
```

## Features Checklist

- [x] Node.js server with Express
- [x] Beautiful modern UI with gradients
- [x] File upload with drag & drop
- [x] Canvas-based frame editor
- [x] Native zoom controls
- [x] Pixel upscaling toggle
- [x] Pan support
- [x] Mouse wheel zoom
- [x] Frame progress tracking
- [x] Undo functionality
- [x] Edit mode for existing templates
- [x] Frame-by-frame navigation in edit mode
- [x] Template management (view/delete)
- [x] Toast notifications
- [x] Responsive design
- [x] Modal for viewing all templates
- [x] RESTful API
- [x] JSON data persistence

## Future Enhancements

- Database integration (SQLite/PostgreSQL)
- User authentication
- Batch template creation
- Export templates to different formats
- Template versioning
- Collaboration features
- Keyboard shortcuts panel
- Image preprocessing (brightness, contrast, etc.)
- Frame templates/presets
- Grid overlay for alignment
- Snap to grid functionality

## License

Proprietary - All rights reserved
