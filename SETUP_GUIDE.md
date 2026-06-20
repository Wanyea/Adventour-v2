# Adventour Social Features Setup Guide

## Overview
This guide will help you implement Firebase authentication, friend system, and collaborative trip planning for your Adventour app.

## Backend Setup (Server/)

### 1. Database Migration
Your existing MySQL database needs to be updated with new tables. Run these SQL commands:

```sql
-- Add new columns to existing User table
ALTER TABLE user 
ADD COLUMN firebase_uid VARCHAR(128) UNIQUE,
ADD COLUMN email VARCHAR(255) UNIQUE,
ADD COLUMN username VARCHAR(100) UNIQUE,
ADD COLUMN display_name VARCHAR(100),
ADD COLUMN profile_picture VARCHAR(500),
ADD COLUMN updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
ADD COLUMN is_active BOOLEAN DEFAULT TRUE;

-- Create new tables for social features
CREATE TABLE friendship (
    id INT PRIMARY KEY AUTO_INCREMENT,
    user_id INT NOT NULL,
    friend_id INT NOT NULL,
    status VARCHAR(20) DEFAULT 'pending',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES user(id),
    FOREIGN KEY (friend_id) REFERENCES user(id),
    UNIQUE KEY unique_friendship (user_id, friend_id)
);

CREATE TABLE trip (
    id INT PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    destination VARCHAR(255),
    start_date DATE,
    end_date DATE,
    created_by INT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE,
    FOREIGN KEY (created_by) REFERENCES user(id)
);

CREATE TABLE trip_member (
    id INT PRIMARY KEY AUTO_INCREMENT,
    trip_id INT NOT NULL,
    user_id INT NOT NULL,
    role VARCHAR(20) DEFAULT 'member',
    joined_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (trip_id) REFERENCES trip(id),
    FOREIGN KEY (user_id) REFERENCES user(id),
    UNIQUE KEY unique_trip_member (trip_id, user_id)
);

CREATE TABLE trip_place (
    id INT PRIMARY KEY AUTO_INCREMENT,
    trip_id INT NOT NULL,
    place_id VARCHAR(50) NOT NULL,
    place_name VARCHAR(255),
    place_address VARCHAR(500),
    place_types VARCHAR(500),
    added_by INT NOT NULL,
    added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    day_number INT,
    order_in_day INT,
    status VARCHAR(20) DEFAULT 'suggested',
    FOREIGN KEY (trip_id) REFERENCES trip(id),
    FOREIGN KEY (added_by) REFERENCES user(id)
);

CREATE TABLE place_rating (
    id INT PRIMARY KEY AUTO_INCREMENT,
    user_id INT NOT NULL,
    place_id VARCHAR(50) NOT NULL,
    rating INT NOT NULL,
    review TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES user(id),
    UNIQUE KEY unique_user_place_rating (user_id, place_id)
);
```

### 2. Firebase Setup
1. Go to [Firebase Console](https://console.firebase.google.com/)
2. Create a new project or use existing one
3. Enable Authentication with Email/Password provider
4. Go to Project Settings > Service Accounts
5. Generate a new private key (JSON file)
6. Upload the JSON file to your server and set the environment variable:
   ```bash
   export FIREBASE_SERVICE_ACCOUNT_PATH="/path/to/your/serviceAccountKey.json"
   ```

### 3. Install Dependencies
```bash
cd Server
pip install firebase-admin==6.4.0 PyJWT==2.8.0
```

### 4. Deploy Updated Backend

App Engine uses `Server/app.yaml` as its deployment manifest. Keep the real
`app.yaml` local because it contains deployment environment variables. Start
from the committed template:

```bash
cd Server
cp app.yaml.example app.yaml
# Edit app.yaml with your Cloud SQL settings and server-side Google Maps key.
gcloud app deploy
```

## Frontend Setup (AdventourApp/)

### 1. Install Dependencies
```bash
cd AdventourApp
npm install @react-native-firebase/app @react-native-firebase/auth @react-navigation/bottom-tabs react-native-vector-icons
```

### 2. Firebase Configuration
1. Download `google-services.json` from Firebase Console
2. Place it in `AdventourApp/android/app/`
3. For iOS, download `GoogleService-Info.plist` and add to your iOS project

### 3. Android Configuration
Add to `android/app/build.gradle`:
```gradle
apply plugin: 'com.google.gms.google-services'
```

Add to `android/build.gradle`:
```gradle
classpath 'com.google.gms:google-services:4.3.15'
```

### 4. iOS Configuration
Add Firebase pods to `ios/Podfile`:
```ruby
pod 'Firebase/Auth'
```

Then run:
```bash
cd ios && pod install
```

## New Features Added

### 1. Authentication System
- **Firebase Authentication**: Secure email/password authentication
- **Token-based API calls**: Automatic token inclusion in requests
- **Legacy support**: Backward compatibility with existing username system

### 2. Friend System
- **Friend requests**: Send and accept friend requests
- **User search**: Find users by username or display name
- **Friend management**: View friends list and manage relationships

### 3. Trip Planning
- **Create trips**: Set name, description, destination, dates
- **Invite friends**: Add friends to trips
- **Collaborative planning**: Add places to trips
- **Trip management**: View and manage your trips

### 4. Enhanced Place Recommendations
- **Place ratings**: Rate places 1-5 stars with reviews
- **Collaborative filtering**: Get recommendations based on friends' ratings
- **Trip-specific recommendations**: Get place suggestions for specific trips

### 5. Social Features
- **User profiles**: Display names, usernames, profile pictures
- **Activity tracking**: Track place interactions and ratings
- **Social discovery**: Find places your friends like

## API Endpoints Added

### Authentication
- `POST /user` - Create new user
- `PUT /user/profile` - Update user profile

### Friends
- `GET /api/friends` - Get friends list
- `GET /api/friends/search` - Search for users
- `POST /api/friends/request` - Send friend request
- `GET /api/friends/requests` - Get pending requests
- `POST /api/friends/respond` - Accept/reject requests

### Trips
- `GET /api/trips` - Get user's trips
- `POST /api/trips` - Create new trip
- `GET /api/trips/{id}` - Get trip details
- `POST /api/trips/{id}/invite` - Invite friend to trip
- `POST /api/trips/{id}/places` - Add place to trip
- `GET /api/trips/{id}/recommendations` - Get collaborative recommendations

### Places
- `POST /places/rate` - Rate a place
- `GET /places/{id}/ratings` - Get place ratings

## Machine Learning Integration (Future)

For the ML-based recommendations you mentioned, consider:

1. **Google Cloud AI Platform**: Train recommendation models
2. **BigQuery**: Analyze user behavior patterns
3. **Cloud Functions**: Real-time ML predictions
4. **Collaborative filtering**: Use friends' preferences
5. **Content-based filtering**: Use place features and user preferences

## Testing the Implementation

1. **Backend**: Test API endpoints with Postman or curl
2. **Frontend**: Run the app and test authentication flow
3. **Database**: Verify new tables are created correctly
4. **Firebase**: Check authentication in Firebase Console

## Next Steps

1. Set up Firebase project and add configuration files
2. Run database migrations
3. Deploy updated backend
4. Install frontend dependencies
5. Test authentication flow
6. Add friends and create trips
7. Test collaborative recommendations

## Troubleshooting

- **Firebase errors**: Check service account configuration
- **Database errors**: Verify migrations ran successfully
- **Frontend build errors**: Check Firebase configuration files
- **Authentication issues**: Verify Firebase project settings

The implementation provides a solid foundation for social features while maintaining backward compatibility with your existing system.
