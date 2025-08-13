# Handoff - Confluence Daily Handoff Manager

A desktop application for managing daily shift handoff documentation in Confluence, designed specifically for GNOC managers to streamline their handoff process.

## 🎯 Purpose

Handoff simplifies the daily shift handover process by providing a centralized tool to:
- View previous day's handoff notes instantly
- Create standardized daily handoff pages
- Edit existing handoff documentation
- Search and manage handoff pages efficiently

## ✨ Features

### 📋 Yesterday's Handoff
- Automatically displays the previous day's handoff page
- Direct view of content without navigation
- Quick access to edit functionality
- Manager-specific content filtering

### 🔍 Search & Edit
- Search for any handoff page by title or date
- WYSIWYG (Visual) editor for easy formatting
- HTML editor for advanced users
- Toggle between visual and code editing modes
- Real-time content updates

### ➕ Create Daily Pages
- Auto-generates page titles with format: `DD-MM-YYYY_Handoff_ManagerName`
- Pre-filled GNOC shift handoff template
- Standardized structure for consistency
- One-click page creation

### 🗑️ Page Management
- Safe deletion with double confirmation
- Search functionality for finding specific pages
- All pages organized under parent page structure

## 📋 Prerequisites

- Python 3.11 or higher
- Confluence account with write permissions
- Personal Access Token (PAT) for Confluence API
- Access to the target Confluence space

## 🚀 Installation

1. Clone the repository:
    ```bash
    git clone https://github.com/yourusername/handoff.git
    cd handoff
    ```

2. Install required dependencies:
    ```bash
    pip install requests
    pip install beautifulsoup4
    pip install tkhtmlview
    pip install python-dotenv
    pip install urllib3
    ```

    or

    ```bash
    pip install -r requirements.txt
    ```

3. Create a `.env` file in the project root:
    ```env
    # Confluence Configuration
    PAT=your_personal_access_token_here
    BASE_URL=https://your-confluence-instance.com
    PAGE_ID=parent_page_id_here
    SPACE_KEY=your_space_key
    MANAGER_NAME=Your_Name
    ```

## 🔧 Configuration

### Environment Variables

| Variable     | Description                                         | Example                              |
|--------------|-----------------------------------------------------|--------------------------------------|
| PAT          | Personal Access Token for Confluence API            | ODYwMjAwNDQ5MTU5O...                  |
| BASE_URL     | Your Confluence instance URL                        | https://confluence.company.com       |
| PAGE_ID      | Parent page ID where handoffs are stored            | 123456789                            |
| SPACE_KEY    | Confluence space key                                | space key                            |
| MANAGER_NAME | Your name for auto-generated titles                 | Jhon                                 |

### Getting Your PAT Token
1. Log into Confluence
2. Go to **Profile → Personal Access Tokens**
3. Create a new token with read/write permissions
4. Copy the token to your `.env` file

## 📝 Usage

Run the application:
```bash
python handoff.py
```

## The application will:

1. Check internet connectivity  
2. Authenticate with Confluence  
3. Display your permission status  
4. Load yesterday's handoff automatically  

### Navigate through tabs:
- **Yesterday's Handoff**: View/edit previous day's notes  
- **Search & Edit**: Find and modify any handoff page  
- **Create Page**: Generate today's handoff document  
- **Delete Page**: Remove outdated pages  
