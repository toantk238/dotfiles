#!/usr/bin/env bash

# WebDriverAgent IPA Build Script
# This script builds WebDriverAgent XCTest Runner for real iOS devices and packages it as an IPA file
# Note: WebDriverAgent is an XCTest bundle, not a regular iOS app, so it uses build-for-testing instead of archive

set -e

# Configuration variables
PROJECT_NAME="WebDriverAgent"
SCHEME="WebDriverAgentRunner"
BUILD_DIR="./build"
RUNNER_APP_NAME="WebDriverAgentRunner-Runner.app"
IPA_NAME="wda.ipa"

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default values
TEAM_ID=""
PROVISIONING_PROFILE=""
BUNDLE_ID=""
SIGNING_METHOD="automatic"
CODE_SIGN_IDENTITY="iPhone Developer"

# Print usage
usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "This script builds WebDriverAgent as an XCTest runner and packages it as an IPA."
    echo ""
    echo "Options:"
    echo "  -t, --team-id TEAM_ID                    Apple Developer Team ID (required)"
    echo "  -p, --profile PROFILE_UUID               Provisioning Profile UUID (for manual signing)"
    echo "  -b, --bundle-id BUNDLE_ID                Custom Bundle ID (default: com.facebook.WebDriverAgentRunner)"
    echo "  -i, --identity IDENTITY                  Code signing identity (default: 'iPhone Developer')"
    echo "  -s, --signing automatic|manual           Signing method (default: automatic)"
    echo "  -h, --help                              Show this help message"
    echo ""
    echo "Examples:"
    echo "  # Automatic signing with Team ID"
    echo "  $0 -t YOUR_TEAM_ID"
    echo ""
    echo "  # Manual signing with provisioning profile (recommended for wildcard profiles)"
    echo "  $0 -s manual -t YOUR_TEAM_ID -p PROFILE_UUID"
    echo ""
    echo "  # Custom bundle ID for free accounts"
    echo "  $0 -t YOUR_TEAM_ID -b com.yourcompany.WebDriverAgentRunner"
    echo ""
    echo "Note: WebDriverAgent is an XCTest runner, not a regular app. It must be built using"
    echo "      'build-for-testing' and packaged manually as an IPA."
    exit 1
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -t|--team-id)
            TEAM_ID="$2"
            shift 2
            ;;
        -p|--profile)
            PROVISIONING_PROFILE="$2"
            SIGNING_METHOD="manual"
            shift 2
            ;;
        -b|--bundle-id)
            BUNDLE_ID="$2"
            shift 2
            ;;
        -i|--identity)
            CODE_SIGN_IDENTITY="$2"
            shift 2
            ;;
        -s|--signing)
            SIGNING_METHOD="$2"
            shift 2
            ;;
        -h|--help)
            usage
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            usage
            ;;
    esac
done

# Validate required parameters
if [ -z "$TEAM_ID" ]; then
    echo -e "${RED}Error: Team ID is required${NC}"
    echo "Use -t or --team-id to specify your Apple Developer Team ID"
    echo ""
    echo "Find your Team ID in:"
    echo "  - Xcode ‚Üí Preferences ‚Üí Accounts ‚Üí View Details"
    echo "  - Apple Developer Portal ‚Üí Membership"
    exit 1
fi

if [ "$SIGNING_METHOD" == "manual" ] && [ -z "$PROVISIONING_PROFILE" ]; then
    echo -e "${RED}Error: Provisioning Profile UUID is required for manual signing${NC}"
    echo "Use -p or --profile to specify your Provisioning Profile UUID"
    exit 1
fi

# Print build configuration
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}WebDriverAgent XCTest Runner Build${NC}"
echo -e "${BLUE}========================================${NC}"
echo "Project: $PROJECT_NAME"
echo "Scheme: $SCHEME"
echo "Build Type: XCTest Runner (build-for-testing)"
echo "Signing Method: $SIGNING_METHOD"
echo "Team ID: $TEAM_ID"
if [ -n "$PROVISIONING_PROFILE" ]; then
    echo "Provisioning Profile: $PROVISIONING_PROFILE"
fi
if [ -n "$BUNDLE_ID" ]; then
    echo "Custom Bundle ID: $BUNDLE_ID"
else
    echo "Bundle ID: com.facebook.WebDriverAgentRunner (default)"
fi
echo "Code Sign Identity: $CODE_SIGN_IDENTITY"
echo -e "${BLUE}========================================${NC}"

# Clean previous builds
echo -e "\n${YELLOW}Step 1: Cleaning previous builds...${NC}"
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"
rm -f "$IPA_NAME"

# Clean Xcode build
xcodebuild clean \
    -project "${PROJECT_NAME}.xcodeproj" \
    -scheme "$SCHEME" \
    2>/dev/null || true

echo -e "${GREEN}‚úì Cleanup complete${NC}"

# Build for testing (XCTest runner approach)
echo -e "\n${YELLOW}Step 2: Building XCTest runner (build-for-testing)...${NC}"
echo -e "${BLUE}Note: Using 'build-for-testing' because WebDriverAgent is an XCTest bundle${NC}"

BUILD_ARGS=(
    build-for-testing
    -project "${PROJECT_NAME}.xcodeproj"
    -scheme "$SCHEME"
    -configuration Release
    -derivedDataPath "$BUILD_DIR"
    -destination "generic/platform=iOS"
    -allowProvisioningUpdates
    ONLY_ACTIVE_ARCH=NO
    ENABLE_BITCODE=NO
    CODE_SIGNING_ALLOWED=YES
)

# Add signing configuration
if [ "$SIGNING_METHOD" == "automatic" ]; then
    BUILD_ARGS+=(
        CODE_SIGN_STYLE=Automatic
        DEVELOPMENT_TEAM="$TEAM_ID"
    )
else
    BUILD_ARGS+=(
        CODE_SIGN_STYLE=Manual
        CODE_SIGN_IDENTITY="$CODE_SIGN_IDENTITY"
        DEVELOPMENT_TEAM="$TEAM_ID"
        PROVISIONING_PROFILE_SPECIFIER="$PROVISIONING_PROFILE"
    )
fi

# Add custom bundle ID if specified
if [ -n "$BUNDLE_ID" ]; then
    BUILD_ARGS+=(PRODUCT_BUNDLE_IDENTIFIER="$BUNDLE_ID")
fi

# Build the XCTest runner
echo -e "${BLUE}Running: xcodebuild ${BUILD_ARGS[@]}${NC}"
if xcodebuild "${BUILD_ARGS[@]}"; then
    echo -e "${GREEN}‚úì XCTest runner built successfully${NC}"
else
    echo -e "${RED}‚úó Failed to build XCTest runner${NC}"
    echo ""
    echo -e "${YELLOW}Troubleshooting tips:${NC}"
    echo "1. Make sure you have a valid provisioning profile"
    echo "2. Check that your signing certificate is installed in Keychain"
    echo "3. For free accounts, use a custom bundle ID: -b com.yourname.WebDriverAgentRunner"
    echo "4. Verify your Team ID is correct"
    echo "5. Try building in Xcode first to resolve any signing issues"
    exit 1
fi

# Locate the Runner app
echo -e "\n${YELLOW}Step 3: Locating WebDriverAgentRunner-Runner.app...${NC}"

RUNNER_APP_PATH=$(find "$BUILD_DIR/Build/Products" -name "$RUNNER_APP_NAME" -type d | grep -v "iphonesimulator" | head -1)

if [ -z "$RUNNER_APP_PATH" ]; then
    echo -e "${RED}‚úó Could not find $RUNNER_APP_NAME${NC}"
    echo ""
    echo "Build output directory:"
    find "$BUILD_DIR/Build/Products" -type d -maxdepth 2 2>/dev/null || echo "No build products found"
    exit 1
fi

echo -e "${GREEN}‚úì Found: $RUNNER_APP_PATH${NC}"

# Verify the app is properly signed
echo -e "\n${YELLOW}Step 4: Verifying code signature...${NC}"
if codesign -v "$RUNNER_APP_PATH" 2>&1; then
    echo -e "${GREEN}‚úì App is properly signed${NC}"
    codesign -dvv "$RUNNER_APP_PATH" 2>&1 | grep -E "Authority|TeamIdentifier|Identifier" || true
else
    echo -e "${RED}‚úó App signature verification failed${NC}"
    exit 1
fi

# Create IPA manually (XCTest runners can't use exportArchive)
echo -e "\n${YELLOW}Step 5: Creating IPA package...${NC}"
echo -e "${BLUE}Note: XCTest runners must be packaged manually (can't use exportArchive)${NC}"

# Create Payload directory structure
PAYLOAD_DIR="$BUILD_DIR/Payload"
rm -rf "$PAYLOAD_DIR"
mkdir -p "$PAYLOAD_DIR"

# Copy the Runner app to Payload
echo "Copying $RUNNER_APP_NAME to Payload directory..."
cp -R "$RUNNER_APP_PATH" "$PAYLOAD_DIR/"

# Remove extended attributes (to avoid issues)
xattr -cr "$PAYLOAD_DIR/$RUNNER_APP_NAME" 2>/dev/null || true

# Create IPA (which is just a zip file with .ipa extension)
cd "$BUILD_DIR"
echo "Creating IPA archive..."
if zip -qr "../$IPA_NAME" Payload; then
    cd ..
    echo -e "${GREEN}‚úì IPA package created successfully${NC}"
else
    cd ..
    echo -e "${RED}‚úó Failed to create IPA package${NC}"
    exit 1
fi

# Get IPA info
IPA_SIZE=$(du -h "$IPA_NAME" | cut -f1)

# Print summary
echo -e "\n${GREEN}========================================${NC}"
echo -e "${GREEN}Build Completed Successfully!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "IPA Details:"
echo "  Location: $(pwd)/$IPA_NAME"
echo "  Size: $IPA_SIZE"
echo "  Type: XCTest Runner App"
echo "  Bundle: $RUNNER_APP_NAME"
echo ""
echo -e "${BLUE}Installation Methods:${NC}"
echo ""
echo "1. Using Xcode:"
echo "   - Open Xcode ‚Üí Window ‚Üí Devices and Simulators"
echo "   - Connect your device"
echo "   - Drag and drop $IPA_NAME onto the device"
echo ""
echo "2. Using Apple Configurator 2:"
echo "   - Download from Mac App Store"
echo "   - Add ‚Üí Apps ‚Üí Choose from my Mac ‚Üí Select $IPA_NAME"
echo ""
echo "3. Using Command Line:"
echo "   ios-deploy --bundle $IPA_NAME"
echo "   OR"
echo "   tidevice install $IPA_NAME"
echo ""
echo -e "${BLUE}For Appium Automation:${NC}"
echo ""
echo "Option 1 - Use the .app bundle directly:"
echo "  appium:prebuiltWDAPath: \"$RUNNER_APP_PATH\""
echo ""
echo "Option 2 - Install IPA first, then reference it:"
echo "  appium:app: \"$(pwd)/$IPA_NAME\""
echo ""
echo -e "${YELLOW}Important Notes:${NC}"
echo "‚Ä¢ WebDriverAgent is an XCTest runner, not a regular iOS app"
echo "‚Ä¢ It starts via 'test-without-building' when used with Appium"
echo "‚Ä¢ The app will appear as 'WebDriverAgentRunner-Runner' on your device"
echo "‚Ä¢ It won't have a visible UI - it runs as a background test service"
echo ""
echo -e "${GREEN}========================================${NC}"

# Cleanup
echo -e "\n${YELLOW}Cleaning up temporary files...${NC}"
# Optionally keep the build directory for debugging
# Uncomment the next line to remove it:
# rm -rf "$BUILD_DIR"
echo -e "${GREEN}‚úì Done!${NC}"
echo ""
echo "Build artifacts are kept in: $BUILD_DIR"
echo "To clean up: rm -rf $BUILD_DIR"
