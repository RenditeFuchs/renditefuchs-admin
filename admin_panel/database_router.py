"""
Database Router for RenditeFuchs Admin Dashboard
Routes core app models to the main database
"""

class DatabaseRouter:
    """
    A router to control all database operations on models
    """
    
    def db_for_read(self, model, **hints):
        """Suggest the database to read from."""
        if model._meta.app_label == 'core':
            return 'main_db'
        return None
    
    def db_for_write(self, model, **hints):
        """Suggest the database to write to."""
        if model._meta.app_label == 'core':
            return 'main_db'
        return None
    
    def allow_relation(self, obj1, obj2, **hints):
        """Allow relations if models are in the same app."""
        return True
    
    def allow_migrate(self, db, app_label, model_name=None, **hints):
        """Ensure that certain apps' models get created on the right database."""
        if app_label == 'core':
            return db == 'main_db'
        return db == 'default'