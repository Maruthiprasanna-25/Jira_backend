class ErrorMessages:
    PROJECT_NOT_FOUND = "Project not found"
    STORY_NOT_FOUND = "Story not found"
    TEAM_NOT_FOUND = "Team not found"
    USER_NOT_FOUND = "User not found"
    NOTIFICATION_NOT_FOUND = "Notification not found"
    REQUEST_NOT_FOUND = "Request not found"
    
    # Auth
    INVALID_CREDENTIALS = "Invalid email or password"
    EMAIL_EXISTS = "Email already registered"
    INVALID_PASSWORD = "Invalid password"
    INVALID_CURRENT_PASSWORD = "Invalid current password"
    INVALID_ROLE = "Invalid role"
    INVALID_MODE = "Invalid mode"
    
    # Permissions
    ACCESS_DENIED = "Access denied"
    NO_PERMISSION_EDIT = "No permission to edit this issue."
    NO_PERMISSION_CREATE = "You do not have permission to create issues in this project."
    ONLY_ADMINS_PROJECT_LEADS = "Only Admins or Project Leads can perform this action"
    PROJECT_INACTIVE = "The project is inactive."
    
    # Hierarchy
    CIRCULAR_DEPENDENCY = "Circular dependency detected."
    INVALID_PARENT = "Invalid parent assignment"

class SuccessMessages:
    PROJECT_ARCHIVED = "Project archived successfully"
    PROJECT_DELETED = "Project deleted successfully"
    TEAM_DELETED = "Team deleted successfully"
    STORY_DELETED = "Story deleted successfully"

class Roles:
    ADMIN = "ADMIN"
    DEVELOPER = "DEVELOPER"
    TESTER = "TESTER"
    MASTER_ADMIN = "MASTER_ADMIN"
    ALL_ROLES = [ADMIN, DEVELOPER, TESTER]