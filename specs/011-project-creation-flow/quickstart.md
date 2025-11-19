# Quickstart: Project Creation Flow

**Feature**: 011-project-creation-flow
**Audience**: Developers implementing or modifying the project creation workflow

## 🚀 5-Minute Implementation Guide

### Prerequisites

- Frontend: Next.js 14, React 18, TypeScript 5.3+, Tailwind CSS
- Backend: Python 3.11, FastAPI, aiosqlite
- Running instance: `codeframe serve` on port 8080

### Step 1: Update Root Page (2 minutes)

**File**: `web-ui/src/app/page.tsx`

```tsx
'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { ProjectCreationForm } from '@/components/ProjectCreationForm';
import { Spinner } from '@/components/Spinner';

export default function HomePage() {
  const router = useRouter();
  const [isCreating, setIsCreating] = useState(false);

  const handleProjectCreated = (projectId: number) => {
    // Redirect to dashboard immediately after creation
    router.push(`/projects/${projectId}`);
  };

  const handleSubmit = () => {
    // Show loading spinner while API request in flight
    setIsCreating(true);
  };

  const handleError = () => {
    // Hide loading spinner on error
    setIsCreating(false);
  };

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center p-4">
      <div className="max-w-2xl w-full">
        {/* Welcome Header */}
        <div className="text-center mb-8">
          <h1 className="text-4xl font-bold text-gray-900 mb-2">
            Welcome to CodeFRAME
          </h1>
          <p className="text-lg text-gray-600">
            AI coding agents that work autonomously while you sleep
          </p>
        </div>

        {/* Form or Loading Spinner */}
        {isCreating ? (
          <div className="text-center">
            <Spinner size="lg" />
            <p className="mt-4 text-gray-600">Creating your project...</p>
          </div>
        ) : (
          <ProjectCreationForm
            onSuccess={handleProjectCreated}
            onSubmit={handleSubmit}
            onError={handleError}
          />
        )}
      </div>
    </div>
  );
}
```

**What This Does**:
- Renders ProjectCreationForm at root route (`/`)
- Shows welcome message above form
- Displays loading spinner during project creation
- Redirects to `/projects/:id` after successful creation

---

### Step 2: Enhance ProjectCreationForm (3 minutes)

**File**: `web-ui/src/components/ProjectCreationForm.tsx`

**Changes Needed**:
1. Add `description` field (textarea, 10-500 chars)
2. Add on-blur validation for name and description
3. Support new callback props (`onSubmit`, `onError`)

**Key Code Snippets**:

**Add Description Field**:
```tsx
// After projectType field
<div className="mb-6">
  <label htmlFor="description" className="block text-sm font-medium text-gray-700 mb-2">
    Description *
  </label>
  <textarea
    id="description"
    value={description}
    onChange={(e) => setDescription(e.target.value)}
    onBlur={() => validateDescription()}  // Validate on blur
    className={`w-full px-4 py-2 border rounded-lg ${
      errors.description ? 'border-red-500' : 'border-gray-300'
    }`}
    rows={4}
    placeholder="Describe what your project will do..."
    disabled={isSubmitting}
    maxLength={500}
  />
  {errors.description && (
    <p className="mt-1 text-sm text-red-600">{errors.description}</p>
  )}
  <p className="mt-1 text-sm text-gray-500">
    {description.length} / 500 characters (min 10)
  </p>
</div>
```

**Add Validation Functions**:
```tsx
const validateName = () => {
  const newErrors = { ...errors };

  if (!name.trim()) {
    newErrors.name = 'Project name is required';
  } else if (name.length < 3) {
    newErrors.name = 'Project name must be at least 3 characters';
  } else if (!/^[a-z0-9-_]+$/.test(name)) {
    newErrors.name = 'Only lowercase letters, numbers, hyphens, and underscores allowed';
  } else {
    delete newErrors.name;
  }

  setErrors(newErrors);
  return Object.keys(newErrors).length === 0;
};

const validateDescription = () => {
  const newErrors = { ...errors };

  if (!description.trim()) {
    newErrors.description = 'Project description is required';
  } else if (description.length < 10) {
    newErrors.description = 'Description must be at least 10 characters';
  } else {
    delete newErrors.description;
  }

  setErrors(newErrors);
  return Object.keys(newErrors).length === 0;
};
```

**Update Submit Handler**:
```tsx
const handleSubmit = async (e: React.FormEvent) => {
  e.preventDefault();

  // Validate all fields
  const nameValid = validateName();
  const descValid = validateDescription();
  if (!nameValid || !descValid) return;

  setIsSubmitting(true);
  onSubmit?.();  // Call parent callback (for loading spinner)

  try {
    const response = await projectsApi.createProject(
      name,
      projectType,
      description  // Include description in API call
    );
    onSuccess(response.data.id);  // Pass project ID to parent

  } catch (error: any) {
    setIsSubmitting(false);
    onError?.(error);  // Call parent error callback
    // ... existing error handling
  }
};
```

---

### Step 3: Create Spinner Component (1 minute)

**File**: `web-ui/src/components/Spinner.tsx` (NEW FILE)

```tsx
interface SpinnerProps {
  size?: 'sm' | 'md' | 'lg';
}

export function Spinner({ size = 'md' }: SpinnerProps) {
  const sizeClasses = {
    sm: 'w-4 h-4 border-2',
    md: 'w-8 h-8 border-3',
    lg: 'w-12 h-12 border-4',
  };

  return (
    <div
      className={`${sizeClasses[size]} border-blue-600 border-t-transparent rounded-full animate-spin`}
      role="status"
      aria-label="Loading"
    />
  );
}
```

**What This Does**:
- Renders spinning circle animation using Tailwind CSS
- Supports 3 sizes: small (16px), medium (32px), large (48px)
- Accessible with `role="status"` and `aria-label`

---

### Step 4: Update API Client (Optional)

**File**: `web-ui/src/lib/api.ts`

**If `createProject()` doesn't accept `description` parameter**, update it:

```typescript
// Before
createProject(name: string, projectType: string): Promise<AxiosResponse<ProjectResponse>>

// After
createProject(
  name: string,
  projectType: string,
  description: string
): Promise<AxiosResponse<ProjectResponse>> {
  return axios.post('/api/projects', { name, projectType, description });
}
```

---

## ✅ Testing Your Implementation

### Manual Test (1 minute)

1. **Start server**: `codeframe serve`
2. **Open browser**: http://localhost:8080
3. **Verify welcome page**:
   - "Welcome to CodeFRAME" heading visible
   - Form with 3 fields: Name, Type (dropdown), Description (textarea)
4. **Test validation**:
   - Leave name empty → Submit → See "Project name is required"
   - Type "ab" in name → Blur → See "Project name must be at least 3 characters"
   - Type "My App!" in name → Blur → See "Only lowercase letters..."
   - Leave description empty → Submit → See "Project description is required"
   - Type "Short" in description → Blur → See "Description must be at least 10 characters"
5. **Test successful creation**:
   - Name: "test-project"
   - Type: Python
   - Description: "A test project for validation"
   - Submit → See loading spinner → Redirect to `/projects/1`

### Automated Tests

```bash
# Run frontend tests
cd web-ui
npm test ProjectCreationForm.test.tsx
npm test Spinner.test.tsx
npm test page.test.tsx

# Run backend tests (if added)
cd ..
uv run pytest tests/api/test_project_creation_api.py -v
```

---

## 🎯 Key Features Implemented

| Feature | Status | Location |
|---------|--------|----------|
| Welcome page at root route | ✅ | `web-ui/src/app/page.tsx` |
| Description field with validation | ✅ | `ProjectCreationForm.tsx` |
| On-blur validation (name, description) | ✅ | `validateName()`, `validateDescription()` |
| Character counter | ✅ | Below description textarea |
| Loading spinner | ✅ | `web-ui/src/components/Spinner.tsx` |
| Automatic redirect after creation | ✅ | `handleProjectCreated()` in HomePage |
| Error handling (duplicate, network) | ✅ | `handleSubmit()` catch block |

---

## 🔧 Troubleshooting

### Issue: Form doesn't show validation errors

**Cause**: On-blur handlers not added to inputs
**Fix**: Add `onBlur={() => validateName()}` to name input, `onBlur={() => validateDescription()}` to description textarea

### Issue: Redirect doesn't work after creation

**Cause**: `onSuccess` callback not called or `router.push()` not executed
**Fix**: Verify `onSuccess(response.data.id)` is called in try block, and HomePage has `handleProjectCreated` wired up

### Issue: Loading spinner doesn't appear

**Cause**: `onSubmit` callback not called or `isCreating` state not set
**Fix**: Verify `onSubmit?.()` is called before API request, and HomePage sets `setIsCreating(true)` in `handleSubmit`

### Issue: Backend rejects description

**Cause**: API client not sending `description` parameter
**Fix**: Update `projectsApi.createProject()` to include `description` in request body

---

## 📚 Related Documentation

- **Feature Spec**: [spec.md](./spec.md) - Full requirements and user stories
- **Implementation Plan**: [plan.md](./plan.md) - Technical approach and architecture
- **Data Model**: [data-model.md](./data-model.md) - State management and validation rules
- **API Contract**: [contracts/api.openapi.yaml](./contracts/api.openapi.yaml) - OpenAPI specification
- **Sprint 9.5**: [../../../sprints/sprint-09.5-critical-ux-fixes.md](../../../sprints/sprint-09.5-critical-ux-fixes.md) - Sprint context

---

## 🚀 Next Steps

After completing this quickstart:

1. **Run tests**: Ensure all test cases pass (≥85% coverage target)
2. **Manual testing**: Verify all user stories from spec.md
3. **Code review**: Self-review or pair review before committing
4. **Commit**: Follow conventional commit format (`feat: add project description field`)
5. **PR**: Create pull request with checklist from spec.md

**Estimated Time to Complete**: ~10 minutes implementation + 15 minutes testing = **25 minutes total**

---

**Ready to implement?** Follow the steps above in order, test as you go, and refer to the full spec for detailed requirements.
