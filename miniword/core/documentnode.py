from ..textmodel.modelbase import Model


class DocumentNode(Model):
    owner = None
    name = None
    def set_owner(self, owner, name):
        """Set the attribute owner and the attribute name."""
        self.owner = owner
        self.name = name
        
    def notify(self, message='model_changed', *args, **kwds):
        """Inform all observers and the owner about the change."""
        self.notify_views(message, *args, **kwds)
        owner = self.owner
        if owner is None:
            return
        if not self._call_if_present(owner, self.name+'_changed', self,
                                     *args, **kwds):
            self._call_if_present(owner, 'attribute_changed', self)
        
        
