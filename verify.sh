#!/bin/bash
# Quick verification script for cf-46 deployment

echo "=== 1. Check if progress method exists in code ==="
if grep -q "_calculate_project_progress" codeframe/persistence/database.py; then
    echo "✅ Progress method EXISTS in database.py"
else
    echo "❌ Progress method NOT FOUND - code not deployed!"
    exit 1
fi

echo -e "\n=== 2. Check API response ==="
RESPONSE=$(curl -s http://localhost:14200/api/projects)
echo "$RESPONSE" | jq '.'

echo -e "\n=== 3. Check if projects exist ==="
PROJECT_COUNT=$(echo "$RESPONSE" | jq 'length')
echo "Projects in database: $PROJECT_COUNT"

if [ "$PROJECT_COUNT" -eq 0 ]; then
    echo "⚠️  No projects in database - cannot test progress field"
    echo "This is OK if database is empty, but means we can't verify the fix"
else
    echo -e "\n=== 4. Check first project has progress field ==="
    PROGRESS=$(echo "$RESPONSE" | jq '.[0].progress')

    if [ "$PROGRESS" = "null" ]; then
        echo "❌ PROBLEM: progress field is NULL!"
        echo "The code has the method, but it's not being called"
    else
        echo "✅ Progress field exists!"
        echo "$PROGRESS" | jq '.'
    fi
fi

echo -e "\n=== 5. PM2 process info ==="
pm2 list | grep codeframe
