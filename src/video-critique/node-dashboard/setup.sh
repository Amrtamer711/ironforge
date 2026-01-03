#!/bin/bash

# Video Critique Dashboard - Setup Script
# This script helps you set up the Node.js dashboard

set -e

echo "╔════════════════════════════════════════════════════════╗"
echo "║   Video Critique Dashboard - Setup                     ║"
echo "╚════════════════════════════════════════════════════════╝"
echo ""

# Check Node.js version
echo "🔍 Checking Node.js version..."
if ! command -v node &> /dev/null; then
    echo "❌ Node.js is not installed!"
    echo "   Please install Node.js 18 or higher from https://nodejs.org/"
    exit 1
fi

NODE_VERSION=$(node -v | cut -d'v' -f2 | cut -d'.' -f1)
if [ "$NODE_VERSION" -lt 18 ]; then
    echo "⚠️  Node.js version is $NODE_VERSION, but 18+ is recommended"
else
    echo "✅ Node.js $(node -v) detected"
fi

# Check npm
echo ""
echo "🔍 Checking npm..."
if ! command -v npm &> /dev/null; then
    echo "❌ npm is not installed!"
    exit 1
fi
echo "✅ npm $(npm -v) detected"

# Check database
echo ""
echo "🔍 Checking database..."
if [ -f "../data/history_logs.db" ]; then
    echo "✅ Database found at ../data/history_logs.db"
else
    echo "⚠️  Database not found at ../data/history_logs.db"
    echo "   The dashboard will not work without the database."
    echo "   Please ensure your database is located in the correct path."
fi

# Install dependencies
echo ""
echo "📦 Installing dependencies..."
npm install

# Create .env if it doesn't exist
if [ ! -f ".env" ]; then
    echo ""
    echo "📝 Creating .env file..."
    cp .env.example .env
    echo "✅ .env file created"
else
    echo ""
    echo "✅ .env file already exists"
fi

echo ""
echo "╔════════════════════════════════════════════════════════╗"
echo "║   Setup Complete!                                      ║"
echo "╚════════════════════════════════════════════════════════╝"
echo ""
echo "🚀 To start the dashboard:"
echo "   npm start"
echo ""
echo "🔧 For development mode (auto-reload):"
echo "   npm run dev"
echo ""
echo "🌐 Dashboard will be available at:"
echo "   http://localhost:3001"
echo ""
echo "📚 For more information, see README.md or QUICKSTART.md"
echo ""
