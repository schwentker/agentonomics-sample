# PawShare - Dog Photo Sharing Platform
## Complete Project Specification

### 🎯 Project Overview

**PawShare** is a modern, full-stack web application for sharing and discovering adorable dog photos. Built with Next.js 14, TypeScript, AWS services, and following comprehensive SDLC best practices.

### ✨ Core Features

- 🔐 **Secure Authentication** - Email/password registration and login with JWT
- 📸 **Photo Upload & Management** - Upload, edit, and delete dog photos with AWS S3
- 🖼️ **Photo Gallery** - Browse and discover photos from the community
- ❤️ **Like System** - Like and unlike photos with real-time updates
- 🔍 **Search & Filter** - Find photos by tags, titles, or descriptions
- 📱 **Responsive Design** - Works perfectly on desktop, tablet, and mobile
- ♿ **Accessibility** - WCAG 2.1 AA compliant with proper ARIA labels
- 🚀 **Performance Optimized** - Core Web Vitals optimized with Next.js Image
- 🔒 **Security First** - Input validation, CORS, rate limiting, and secure headers
- 🧪 **Comprehensive Testing** - Unit, integration, and E2E tests with Playwright

---

## 🛠️ Technology Stack

### Frontend
- **Next.js 14** - React framework with App Router
- **TypeScript** - Type-safe development
- **Tailwind CSS** - Utility-first styling with custom design system
- **React Hook Form** - Form handling with validation
- **Zod** - Schema validation
- **Framer Motion** - Smooth animations
- **Heroicons** - Beautiful SVG icons

### Backend
- **Next.js API Routes** - Serverless API endpoints
- **AWS DynamoDB** - NoSQL database for users and photos
- **AWS S3** - File storage with CloudFront CDN
- **JWT** - Authentication tokens
- **bcryptjs** - Password hashing
- **Multer** - File upload handling

### Testing & Quality
- **Jest** - Unit and integration testing
- **React Testing Library** - Component testing
- **Playwright** - End-to-end testing with browser diagnostics
- **ESLint & Prettier** - Code quality and formatting
- **Husky** - Git hooks for quality gates
- **TypeScript** - Static type checking

### DevOps & Deployment
- **AWS CDK/Terraform** - Infrastructure as Code
- **GitHub Actions** - CI/CD pipeline
- **Docker** - Containerization
- **AWS Amplify** - Deployment platform

---

## 📁 Project Structure

```
src/
├── app/                    # Next.js App Router
│   ├── api/               # API routes
│   │   ├── auth/          # Authentication endpoints
│   │   │   ├── login/     # Login endpoint
│   │   │   └── register/  # Registration endpoint
│   │   └── photos/        # Photo management endpoints
│   │       ├── route.ts   # GET/POST photos
│   │       └── [id]/      # Individual photo operations
│   ├── dashboard/         # Dashboard pages
│   │   └── page.tsx       # REQUIRED: Dashboard page component
│   ├── gallery/           # Gallery pages
│   │   └── page.tsx       # REQUIRED: Gallery page component
│   ├── upload/            # Upload pages
│   │   └── page.tsx       # REQUIRED: Upload page component
│   ├── auth/              # Auth pages
│   │   └── page.tsx       # REQUIRED: Auth page component
│   ├── layout.tsx         # Root layout
│   ├── page.tsx           # Homepage
│   └── globals.css        # Global styles
├── components/            # React components
│   ├── ui/               # Reusable UI components
│   │   ├── Button.tsx    # Button component
│   │   ├── Input.tsx     # Input component
│   │   └── LoadingSpinner.tsx
│   ├── forms/            # Form components
│   │   └── AuthForm.tsx  # Authentication form
│   └── layout/           # Layout components
├── lib/                  # Utility libraries
│   ├── auth/             # Authentication utilities
│   │   ├── jwt.ts        # JWT handling
│   │   ├── password.ts   # Password hashing
│   │   └── middleware.ts # Auth middleware
│   ├── db/               # Database operations
│   │   ├── users.ts      # User operations
│   │   ├── photos.ts     # Photo operations
│   │   └── schema.ts     # Database schemas
│   └── storage/          # File storage utilities
│       └── s3.ts         # S3 operations
├── types/                # TypeScript type definitions
└── utils/                # General utilities

llms/                     # Development artifacts
├── working/              # Temporary files and test artifacts
│   ├── dog-photos/       # Sample dog photos for gallery population
│   │   ├── golden-retriever-1.jpg
│   │   ├── labrador-puppy.jpg
│   │   ├── husky-outdoor.jpg
│   │   ├── beagle-playing.jpg
│   │   └── [additional sample photos]
│   ├── playwright/       # Playwright test artifacts
│   │   ├── screenshots/  # Test screenshots
│   │   ├── videos/       # Test recordings
│   │   └── reports/      # Test reports
│   └── server-manager/   # Server process management
├── scripts/              # Development scripts
│   └── demo/             # Demo scripts
└── project-docs/         # Project documentation
│   └── index.ts          # All type definitions
├── utils/                # General utilities
└── hooks/                # Custom React hooks

tests/
├── unit/                 # Unit tests
├── integration/          # Integration tests
└── e2e/                  # End-to-end tests
    ├── auth.spec.ts      # Authentication tests
    ├── dashboard.spec.ts # Dashboard tests
    └── global-setup.ts   # Test setup

.amazonq/
├── rules/                # Development rules and standards
└── deployment-config.json # Deployment configuration
```

---

## 🎨 Design System

### Color Palette
```javascript
colors: {
  primary: {
    50: '#fef7ee',   // Light orange tints
    500: '#ed7420',  // Main orange
    900: '#762e17',  // Dark orange
  },
  secondary: {
    50: '#f0f9ff',   // Light blue tints
    500: '#0ea5e9',  // Main blue
    900: '#0c4a6e',  // Dark blue
  },
  accent: {
    50: '#fefce8',   // Light yellow tints
    500: '#eab308',  // Main yellow
    900: '#713f12',  // Dark yellow
  }
}
```

### Typography
- **Font Family**: Inter (Google Fonts)
- **Font Weights**: 300, 400, 500, 600, 700, 800, 900
- **Responsive Typography**: Mobile-first approach

### Shadows & Effects
- **Soft Shadow**: Subtle depth for cards
- **Medium Shadow**: Interactive elements
- **Large Shadow**: Modals and overlays
- **Gradient Backgrounds**: Primary to secondary colors

---

## 🔧 Core Components

### 1. Authentication System

#### AuthForm Component
```typescript
interface AuthFormProps {
  mode: 'login' | 'register';
  onSubmit: (data: LoginInput | CreateUserInput) => Promise<void>;
  loading: boolean;
  error: string;
  onModeChange: (mode: 'login' | 'register') => void;
  className?: string;
}
```

**Features:**
- Form validation with Zod schemas
- Password visibility toggle
- Loading states and error handling
- Responsive design with proper accessibility

#### API Endpoints
- `POST /api/auth/register` - User registration
- `POST /api/auth/login` - User authentication
- JWT token generation and validation

### 2. Photo Management System

#### Photo Upload
```typescript
interface CreatePhotoInput {
  title: string;
  description?: string;
  tags: string[];
  file: File;
}
```

**Features:**
- Drag & drop file upload
- Image compression and optimization
- S3 storage with CloudFront CDN
- Thumbnail generation

#### Photo Gallery
```typescript
interface Photo {
  id: string;
  userId: string;
  title: string;
  description?: string;
  imageUrl: string;
  thumbnailUrl: string;
  tags: string[];
  likes: number;
  likedBy: string[];
  createdAt: string;
  updatedAt: string;
  user?: User;
}
```

**Features:**
- Infinite scroll pagination
- Search and filter functionality
- Like/unlike system
- Responsive grid layout
- **Sample Photo Population** - Pre-populate gallery with sample dog photos from `llms/working/dog-photos/` directory for demonstration and testing purposes

**Sample Photo Integration:**
- Load sample dog photos from the `llms/working/dog-photos/` directory during development
- Create mock photo entries with realistic metadata (titles, descriptions, tags)
- Ensure sample photos demonstrate various breeds, activities, and scenarios
- Use sample photos for E2E testing and demo purposes
- Sample photos should include diverse content: puppies, adult dogs, different breeds, indoor/outdoor settings

**Sample Photo Requirements:**
- **Minimum 10-15 sample photos** covering different dog breeds and scenarios
- **Metadata Requirements**: Each sample photo should have:
  - Descriptive title (e.g., "Golden Retriever Playing Fetch")
  - Engaging description (e.g., "Max loves playing fetch in the park on sunny afternoons!")
  - Relevant tags (e.g., ["golden-retriever", "playful", "outdoor", "fetch"])
  - Realistic like counts for testing
- **File Formats**: JPEG, PNG, WebP (optimized for web)
- **Image Sizes**: Various dimensions to test responsive layout
- **Content Diversity**: Indoor/outdoor, different lighting, various poses and activities

### 3. User Interface Components

#### Button Component
```typescript
interface ButtonProps {
  variant: 'primary' | 'secondary' | 'outline' | 'ghost';
  size: 'sm' | 'md' | 'lg';
  loading?: boolean;
  disabled?: boolean;
  children: React.ReactNode;
  onClick?: () => void;
}
```

#### Input Component
```typescript
interface InputProps {
  type: 'text' | 'email' | 'password' | 'search';
  placeholder?: string;
  error?: string;
  icon?: React.ComponentType;
  value: string;
  onChange: (value: string) => void;
}
```

---

## 🗄️ Database Schema

### DynamoDB Tables

#### Users Table
```typescript
interface User {
  PK: string;           // USER#${userId}
  SK: string;           // USER#${userId}
  id: string;
  email: string;
  name: string;
  passwordHash: string;
  avatar?: string;
  createdAt: string;
  updatedAt: string;
  GSI1PK: string;       // EMAIL#${email}
  GSI1SK: string;       // USER#${userId}
}
```

#### Photos Table
```typescript
interface Photo {
  PK: string;           // PHOTO#${photoId}
  SK: string;           // PHOTO#${photoId}
  id: string;
  userId: string;
  title: string;
  description?: string;
  imageUrl: string;
  thumbnailUrl: string;
  s3Key: string;
  tags: string[];
  likes: number;
  likedBy: string[];
  createdAt: string;
  updatedAt: string;
  GSI1PK: string;       // USER#${userId}
  GSI1SK: string;       // PHOTO#${createdAt}
}
```

### Global Secondary Indexes
- **GSI1**: Query photos by user
- **GSI2**: Query users by email
- **GSI3**: Query photos by tags

---

## 🔒 Security Implementation

### Authentication & Authorization
- JWT tokens with secure HTTP-only cookies
- Password hashing with bcrypt (12 rounds)
- Rate limiting on auth endpoints
- CORS configuration for allowed origins

### Input Validation
- Zod schemas for all API inputs
- File type and size validation
- SQL injection prevention
- XSS protection with sanitization

### Security Headers
```javascript
const securityHeaders = {
  'X-DNS-Prefetch-Control': 'on',
  'Strict-Transport-Security': 'max-age=63072000',
  'X-XSS-Protection': '1; mode=block',
  'X-Frame-Options': 'SAMEORIGIN',
  'X-Content-Type-Options': 'nosniff',
  'Referrer-Policy': 'origin-when-cross-origin',
}
```

---

## 🧪 Testing Strategy

### Unit Tests (Jest + React Testing Library)
- Component rendering and behavior
- Utility function testing
- Custom hooks testing
- API route testing

### Integration Tests
- Database operations
- Authentication flows
- File upload processes
- API endpoint integration

### End-to-End Tests (Playwright)
**MANDATORY: Follow Playwright Browser Diagnostics Standards**

#### Required E2E Test Coverage:
```typescript
// Critical user journeys
- User registration and login
- Photo upload and management
- Gallery browsing and search
- Like/unlike functionality
- Responsive design testing
- Cross-browser compatibility
- Accessibility compliance
- Performance metrics
```

#### Sample Photo Testing Requirements:
- **Gallery Population**: Use sample dog photos from `llms/working/dog-photos/` to populate gallery for testing
- **Search Testing**: Test search functionality with diverse sample photo metadata
- **Filter Testing**: Verify tag-based filtering using sample photo tags
- **Like System Testing**: Test like/unlike functionality on sample photos
- **Performance Testing**: Measure gallery load times with realistic photo content
- **Visual Regression**: Use sample photos for consistent visual testing

#### Browser Diagnostics Requirements:
- **Console Log Monitoring**: Capture all browser console messages
- **Network Request Analysis**: Monitor all HTTP requests and responses
- **Rendered HTML Capture**: Save actual DOM content at key points
- **Dev Tools Simulation**: Inspect computed styles and element properties
- **Screenshot Documentation**: Capture visual state at every major step
- **Video Recording**: Record complex user interactions
- **Comprehensive Reporting**: Generate detailed diagnostic reports

### Performance Testing
- Core Web Vitals monitoring
- Bundle size analysis
- Image optimization verification
- Loading time measurements

---

## 🚀 Deployment & Infrastructure

### AWS Infrastructure
```yaml
Resources:
  - DynamoDB Tables (Users, Photos)
  - S3 Bucket (Photo storage)
  - CloudFront Distribution (CDN)
  - Lambda Functions (Image processing)
  - API Gateway (Rate limiting)
  - CloudWatch (Monitoring)
```

### CI/CD Pipeline
```yaml
stages:
  - Code Quality (ESLint, Prettier, TypeScript)
  - Unit Tests (Jest)
  - Integration Tests
  - E2E Tests (Playwright with full diagnostics)
  - Security Scan
  - Build & Deploy
  - Smoke Tests
```

### Environment Configuration
- **Development**: Local development with hot reload
- **Staging**: Production-like environment for testing
- **Production**: Optimized build with CDN and caching

---

## 📊 Performance Requirements

### Core Web Vitals Targets
- **LCP (Largest Contentful Paint)**: < 2.5s
- **FID (First Input Delay)**: < 100ms
- **CLS (Cumulative Layout Shift)**: < 0.1

### Optimization Strategies
- Next.js Image component for automatic optimization
- Code splitting and lazy loading
- CDN for static assets
- Database query optimization
- Caching strategies (browser, CDN, API)

---

## ♿ Accessibility Standards

### WCAG 2.1 AA Compliance
- Semantic HTML structure
- Proper ARIA labels and roles
- Keyboard navigation support
- Screen reader compatibility
- Color contrast ratios (4.5:1 minimum)
- Focus management and indicators

### Implementation Details
- Alt text for all images
- Form labels and error messages
- Skip navigation links
- Accessible color palette
- Responsive text sizing

---

## 🔧 Development Workflow

### Git Workflow
- **Main Branch**: Production-ready code
- **Develop Branch**: Integration branch
- **Feature Branches**: Individual features
- **Hotfix Branches**: Critical fixes

### Code Quality Gates
- Pre-commit hooks (Husky)
- Automated linting and formatting
- Type checking with TypeScript
- Test coverage requirements
- Security vulnerability scanning

### Documentation Requirements
- API documentation (OpenAPI/Swagger)
- Component documentation (Storybook)
- README with setup instructions
- Architecture decision records (ADRs)

---

## 📈 Monitoring & Analytics

### Application Monitoring
- Error tracking and alerting
- Performance monitoring (APM)
- User analytics and behavior
- Infrastructure monitoring

### Key Metrics
- User engagement (DAU, MAU)
- Photo upload rates
- Search and discovery usage
- Performance metrics
- Error rates and types

---

## 🚦 Implementation Phases

### Phase 1: Foundation (Week 1-2)
- Project setup and configuration
- Authentication system
- Basic UI components
- Database schema implementation

### Phase 2: Core Features (Week 3-4)
- Photo upload functionality
- Gallery and search
- Like system
- User dashboard
- **Sample Photo Integration** - Populate gallery with sample dog photos from `llms/working/dog-photos/` for demonstration and testing

### Phase 3: Enhancement (Week 5-6)
- Advanced search and filters
- Performance optimization
- Accessibility improvements
- Mobile responsiveness

### Phase 4: Testing & Deployment (Week 7-8)
- Comprehensive testing suite
- E2E tests with browser diagnostics
- Security audit
- Production deployment

---

## 🎯 Success Criteria

### Technical Requirements
- ✅ All tests passing (unit, integration, E2E)
- ✅ Core Web Vitals targets met
- ✅ WCAG 2.1 AA compliance
- ✅ Security audit passed
- ✅ Performance benchmarks achieved

### User Experience
- ✅ Intuitive navigation and workflows
- ✅ Fast loading times across devices
- ✅ Responsive design on all screen sizes
- ✅ Accessible to users with disabilities
- ✅ Error handling and user feedback

### Business Goals
- ✅ User registration and engagement
- ✅ Photo sharing and discovery
- ✅ Community building features
- ✅ Scalable architecture
- ✅ Maintainable codebase

---

## 📚 Additional Resources

### Documentation Links
- [Next.js Documentation](https://nextjs.org/docs)
- [Tailwind CSS Documentation](https://tailwindcss.com/docs)
- [AWS SDK Documentation](https://docs.aws.amazon.com/sdk-for-javascript/)
- [Playwright Testing](https://playwright.dev/docs/intro)

### Development Standards
- Follow all rules in `.amazonq/rules/` directory
- Implement comprehensive browser diagnostics for E2E tests
- Use evidence-based development methodology
- Maintain systematic debugging practices
- Follow timeout and process management standards

---

This specification provides a complete blueprint for building the PawShare dog photo sharing platform from scratch, incorporating all the established development standards, testing requirements, and architectural decisions found in the current project.
