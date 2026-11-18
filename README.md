# Directory Structure
```bash
.
├── bot
│   ├── discord
│   └── telegram
├── meta_service
│   ├── facebook
│   ├── instagram
│   └── whatsapp
├── misc
└── youtube
```

## YouTube upload component

See [YouTube setup and upload instructions](youtube/README.md). The component exposes
POST `/uploading`, accepting a video and channel OAuth credentials from the main app.
