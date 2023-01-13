"""
This module contains the all the base classes necessaries to display different properties of instruments.
The goal is to have a base design so that implementing further GUIS is simplified and can be done without repeating
much code. To implement your own GUI you just need to inherit any particular part you want to customize.

The assembled widget uses a TreeView to display some attribute of the passed instrument.
It will go through the submodules contained in it and display them accordingly

All the classes here assume that arguments present in them will exist in inherited ones. E.g.: all classes
assume that the items used have a property star and trash. If your implementation of ItemBase deletes those properties
unexpected things might break.

You should be careful when using Signals:
I tried keeping signals and direct interaction between classes to a minimum, however,
there still is a need for inter object signal connection.
This is the responsibility of the InstrumentDisplayBase (or whatever your specific widget implementation is).
If you are adding more connections that happen between signals it is recommended to overload the
connectSignals function, call the super version and add whatever new signals you need.
The exception is with the toolbar actions themselves, those are handled by the makeToolBar function.
"""

from pprint import pprint

from instrumentserver import QtCore, QtGui, QtWidgets


class ItemBase(QtGui.QStandardItem):
    """
    Base item for instrument models.

    :param name: The name. This should include all of the submodules.
    :param star: indicates if the item is starred.
    :param trash: indicates if the item is trashed.
    :param extra_obj: The object we want to store here, this can be a parameter or a method at the moment.
        If this is None, it means that the item is a submodule and should only be there to store the children.
    """

    def __init__(self, name, star=False, trash=False, extra_obj=None, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.name = name
        self.star = star
        self.trash = trash
        self.extra_obj = extra_obj

        self.setText(self.name)


class InstrumentModelBase(QtGui.QStandardItemModel):
    """
    Base model used to display information of an instrument (like parameters or methods)

    You need to indicate the instrument and a dictionary from which you want to get the things.

    :param instrument: The instrument we are trying to show.
    :param attr: The string name of the dictionary of the items we want to show ("parameters", for example)
    :param customItem: The item class the model should use.
    """

    def __init__(self, instrument, attr: str, itemClass: ItemBase = ItemBase, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.instrument = instrument
        # Indicates the name of the attributes we are creating the model: Parameters or methods for now.
        self.attr = attr
        self.objectDictionary = getattr(self.instrument, self.attr)
        self.itemClass: ItemBase = itemClass

        self.setHorizontalHeaderLabels([attr])

        self.loadItems()

    def loadItems(self, module=None, prefix=None):
        """
        The argument for either submodules or the instrument itself, since it does not matter, it needs to go through
        all of them

        :param module: A proxy instrument from which we want to add all of its attributes and submodules.
            If `None`, self.instrument will be used.
        """
        if module is None:
            module = self.instrument

        for objectName, obj in getattr(module, self.attr).items():
            # addItem only requires fullName, everything else is going to be passed as args and kwargs to the item
            # constructor
            if prefix is not None:
                objectName = '.'.join([prefix, objectName])
            self.addItem(fullName=objectName, star=False, trash=False, extra_obj=obj)

        for submodName, submod in module.submodules.items():
            if prefix is not None:
                submodName = '.'.join([prefix, submodName])
            self.loadItems(submod, submodName)

    def _addChildTo(self, parent, item):
        if parent == self:
            self.setItem(self.rowCount(), 0, item)
        else:
            parent.appendRow(item)

    def addItem(self, fullName, *args, **kwargs):
        """
        Adds an item to the model. The *args and **kwargs are whatever the specific item needs for a new item.

        :param fullName: The name of the parameter
        """
        path = fullName.split('.')[:-1]
        paramName = fullName.split('.')[-1]

        parent = self
        smName = None
        for sm in path:
            if smName is None:
                smName = sm
            else:
                smName = smName + f".{sm}"

            items = self.findItems(smName, QtCore.Qt.MatchExactly | QtCore.Qt.MatchRecursive, 0)

            if len(items) == 0:
                subModItem = self.itemClass(smName, False, False, None)
                self._addChildTo(parent, subModItem)
                parent = subModItem
            else:
                parent = items[0]

        newItem = self.itemClass(fullName, *args, **kwargs)
        self._addChildTo(parent, newItem)

        return newItem

    def removeItem(self, fullName):
        items = self.findItems(fullName, QtCore.Qt.MatchExactly | QtCore.Qt.MatchRecursive, 0)

        if len(items) > 0:
            item = items[0]
            parent = item.parent()
            if isinstance(parent, self.itemClass):
                parent.removeRow(item.row())
                if parent.rowCount() == 0:
                    self.removeItem(parent.name)
            else:
                self.removeRow(item.row())

    @QtCore.Slot(ItemBase)
    def onItemStarToggle(self, item):
        assert isinstance(item, ItemBase)
        if item.star:
            item.star = False
            item.setIcon(QtGui.QIcon())
        else:
            item.star = True
            item.trash = False
            item.setIcon(QtGui.QIcon(':/icons/star.svg'))

    @QtCore.Slot(ItemBase)
    def onItemTrashToggle(self, item):
        assert isinstance(item, ItemBase)
        if item.trash:
            item.trash = False
            item.setIcon(QtGui.QIcon())
        else:
            item.trash = True
            item.star = False
            item.setIcon(QtGui.QIcon(':/icons/trash.svg'))


class InstrumentSortFilterProxyModel(QtCore.QSortFilterProxyModel):

    def __init__(self, sourceModel: InstrumentModelBase, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.setSourceModel(sourceModel)
        self.setRecursiveFilteringEnabled(True)
        self.setDynamicSortFilter(True)

        self.star = False
        self.trash = False

    @QtCore.Slot(int, QtCore.Qt.SortOrder)
    def onSortingIndicatorChanged(self, index, sortingOrder):
        self.sort(index, sortingOrder)

    def onToggleStar(self):
        if self.star:
            self.star = False
        else:
            self.star = True
        self.invalidateFilter()
        self.sort(0, self.sortOrder())

    def onToggleTrash(self):
        if self.trash:
            self.trash = False
        else:
            self.trash = True
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent: QtCore.QModelIndex) -> bool:
        """
        Calls for the super() unless trash is active and the item or one of its parent is trash.
        """
        parent = self.sourceModel().itemFromIndex(source_parent)
        if parent is None:
            item = self.sourceModel().item(source_row, 0)
        else:
            item = parent.child(source_row, 0)

        # The order in which things get constructed seems to impact this.
        # When the application is first starting, the  proxy model does not have the trash attribute.
        if hasattr(self, 'trash'):
            if self.trash:
                if self._isParentTrash(parent) or item.trash:
                    return False

        return super().filterAcceptsRow(source_row, source_parent)

    def _isParentTrash(self, parent):
        """
        Recursive function to see if any parent of an item is trash.
        """
        if parent is None:
            return False

        if parent.trash:
            return True

        return self._isParentTrash(parent.parent())

    def lessThan(self, left: QtCore.QModelIndex, right: QtCore.QModelIndex) -> bool:
        """
        If star is active, we want the star items to always be on the top.
        """

        # The order in which things get constructed seems to impact this.
        # When the application is first starting, the  proxy model does not have the star attribute.
        if hasattr(self, 'star'):
            if self.star:
                leftItem = self.sourceModel().itemFromIndex(left)
                rightItem = self.sourceModel().itemFromIndex(right)

                if self.sortOrder() == QtCore.Qt.DescendingOrder:
                    if rightItem.star and not leftItem.star:
                        return True
                    elif not rightItem.star and leftItem.star:
                        return False

                elif self.sortOrder() == QtCore.Qt.AscendingOrder:
                    if rightItem.star and not leftItem.star:
                        return False
                    elif not rightItem.star and leftItem.star:
                        return True

        return super().lessThan(left, right)


class InstrumentTreeViewBase(QtWidgets.QTreeView):

    #: Signal(ItemBase)
    #: emitted when this item got its trashed action triggered.
    itemTrashToggle = QtCore.Signal(ItemBase)

    #: Signal(ItemBase)
    #: emitted when this item got its star action triggered.
    itemStarToggle = QtCore.Signal(ItemBase)

    def __init__(self, model, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.setModel(model)

        # We need to turn sorting off so that the view sorting does not interfere with the proxy model sorting.
        self.setSortingEnabled(False)

        # The tree should not have anything to do with filtering itself since that is left for the proxy model.
        self.header().setSortIndicatorShown(True)
        self.header().setSectionsClickable(True)

        self.setAlternatingRowColors(True)

        self.starIcon = QtGui.QIcon(':/icons/star.svg')
        self.starCrossedIcon = QtGui.QIcon(':/icons/star-crossed.svg')
        self.trashIcon = QtGui.QIcon(':/icons/trash.svg')
        self.trashCrossedIcon = QtGui.QIcon(':/icons/trash-crossed')

        self.starItemAction = QtWidgets.QAction(self.starIcon, 'Star Item')
        self.starItemAction.triggered.connect(self.onStarActionTrigger)
        self.trashItemAction = QtWidgets.QAction(self.trashIcon, 'Trash Item')
        self.trashItemAction.triggered.connect(self.onTrashActionTrigger)

        self.contextMenu = QtWidgets.QMenu(self)
        self.contextMenu.addAction(self.starItemAction)
        self.contextMenu.addAction(self.trashItemAction)

        self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.onContextMenuRequested)

        self.lastSelectedItem = None

    @QtCore.Slot(QtCore.QPoint)
    def onContextMenuRequested(self, pos):

        # We get the item from the real model, not the proxy model
        originalModel = self.model().sourceModel()
        proxyIndex = self.indexAt(pos)
        index = self.model().mapToSource(proxyIndex)

        item = originalModel.itemFromIndex(index)

        # if item is none the user right clicked in an empty part of the widget
        if item is not None:
            self.lastSelectedItem = item

            if item.star:
                self.starItemAction.setText('un-star item')
                self.starItemAction.setIcon(self.starCrossedIcon)
            else:
                self.starItemAction.setText('star item')
                self.starItemAction.setIcon(self.starIcon)

            if item.trash:
                self.trashItemAction.setText('un-trash item')
                self.trashItemAction.setIcon(self.trashCrossedIcon)
            else:
                self.trashItemAction.setText('trash item')
                self.trashItemAction.setIcon(self.trashIcon)

            self.contextMenu.exec_(self.mapToGlobal(pos))

    @QtCore.Slot()
    def onStarActionTrigger(self):
        self.itemStarToggle.emit(self.lastSelectedItem)

    @QtCore.Slot()
    def onTrashActionTrigger(self):
        self.itemTrashToggle.emit(self.lastSelectedItem)


class InstrumentDisplayBase(QtWidgets.QWidget):
    """
    Basic widget. To implement new toolbars overload the makeToolBar function. To connect any extra signals overload the connectSignals function.
    """
    def __init__(self, instrument,
                 attr: str,
                 itemClass = ItemBase,
                 modelType = InstrumentModelBase,
                 proxyModelType = InstrumentSortFilterProxyModel,
                 viewType = InstrumentTreeViewBase,
                 *args, **kwargs):
        super().__init__(*args, **kwargs)

        # initializing variables
        self.instrument = instrument
        self.attr = attr
        self.itemClass = itemClass

        # initializing all the different classes
        self.model = modelType(instrument, attr, itemClass, parent=self)
        self.proxyModel = proxyModelType(self.model)
        self.view = viewType(self.proxyModel)

        self.layout_ = QtWidgets.QVBoxLayout()

        self.toolBar, self.lineEdit = self.makeToolbar()
        self.layout_.addWidget(self.toolBar)

        self.layout_.addWidget(self.view)

        self.setLayout(self.layout_)

        self.connectSignals()

    def connectSignals(self):
        self.view.itemStarToggle.connect(self.model.onItemStarToggle)
        self.view.itemTrashToggle.connect(self.model.onItemTrashToggle)

        self.lineEdit.textChanged.connect(self.proxyModel.setFilterRegExp)

        self.view.header().sortIndicatorChanged.connect(self.proxyModel.onSortingIndicatorChanged)

    def makeToolbar(self):
        toolbar = QtWidgets.QToolBar(self)
        toolbar.setIconSize(QtCore.QSize(16, 16))

        refreshAction = toolbar.addAction(
            QtGui.QIcon(":/icons/refresh.svg"),
            "refresh all parameters from the instrument",
        )
        # refreshAction.triggered.connect(lambda x: self.refreshAll())

        toolbar.addSeparator()

        expandAction = toolbar.addAction(
            QtGui.QIcon(":/icons/expand.svg"),
            "expand the parameter tree",
        )
        expandAction.triggered.connect(lambda x: self.view.expandAll())

        collapseAction = toolbar.addAction(
            QtGui.QIcon(":/icons/collapse.svg"),
            "collapse the parameter tree",
        )
        collapseAction.triggered.connect(lambda x: self.view.collapseAll())

        toolbar.addSeparator()

        starAction = toolbar.addAction(
            QtGui.QIcon(':/icons/star.svg'),
            "Move Starred items to the top"
        )
        starAction.setCheckable(True)
        starAction.triggered.connect(lambda x: self.promoteStar())

        trashAction = toolbar.addAction(
            QtGui.QIcon(":/icons/trash-crossed.svg"),
            "Hide trashed items"
        )
        trashAction.setCheckable(True)
        trashAction.triggered.connect(lambda x: self.hideTrash())

        # Debugging tools keep commented for commits.
        # printAction = toolbar.addAction(
        #     QtGui.QIcon(":/icons/code.svg"),
        #     "print empty space",
        # )
        # printAction.triggered.connect(self.debuggingMethod)
        #
        # toolbar.addSeparator()

        filterEdit = QtWidgets.QLineEdit(self)
        filterEdit.setPlaceholderText(f"Filter {self.attr}")

        toolbar.addWidget(filterEdit)

        return toolbar, filterEdit

    @QtCore.Slot()
    def hideTrash(self):
        self.proxyModel.onToggleTrash()

    @QtCore.Slot()
    def promoteStar(self):
        self.proxyModel.onToggleStar()

    def debuggingMethod(self):
        """
        This is just a debugging method.
        """
        items = {}

        def fillChildren(parent):
            for i in range(parent.rowCount()):
                item = parent.child(i, 0)
                items[item.name] = {'item': item, 'star': item.star, 'trash': item.trash}
                if item.hasChildren():
                    fillChildren(item)

        for i in range(self.model.rowCount()):
            item = self.model.item(i, 0)
            items[item.name] = {'item': item, 'star': item.star, 'trash': item.trash}
            if item.hasChildren():
                fillChildren(item)

        pprint(items)
        print("\n \n \n \n")

