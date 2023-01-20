"""
Quick Introduction
==================

This module contains the all the base classes necessaries to display different properties dictionaries of instruments.
The goal is to have a base design such that implementing further GUIS is simplified and can be done without repeating
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

Full Description
================

The following is a more through and linear guide on how to implement your own custom instrument widgets.

The goal of any widget implementation of the following classes is to display some attribute of a Qcodes instrument.
Following this design will allow you to display items similarly to how the generic gui for instruments looks like. It
is recommended to understand the basic of model/view in Qt to more easily understand this guide, but I would do my
best to guide you through.

Classes
-------

ItemBase
^^^^^^^^

This is based of the QStandardItem. It does not do much other than hold the individual data of each item. The actual
object that you are interested in displaying is stored in the variable element.

InstrumentModelBase
^^^^^^^^^^^^^^^^^^^

Based on a QStandardItemModel, it stores all the items in the correct structure. It is in charge of keeping its data
up to date (if needed). All the information of the model is contained in the column 0, this includes any
hierarchical (items inside of items representing submodules) or any other information that should be shown in other
columns. When adding items to the model, use the addItem method, this will take care of hierarchical things for you.
**don't use insertItemTo** This should just be used to insert the correct number of items to the correct place.

Things to pay attention when implementing your own:
    * If your model is going to display more than one column (this is usually the case) you need to set the correct
     number of columns and set the horizontal headers.
    * Implement the function insertItemTo: This is the only function that actually adds items to the model. When the
     model contains more than one column this function creates QStandardItems and adds them to the correct columns.
     **don't forget** to emit the newItem signal if you are going to implement a view that utilizes delegates.

InstrumentSortFilterProxyModel
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

This class is in charge of filtering and sorting of the model. For most things you should not have to care about this
class.

It might be helpful to know, before a new filtering happens, the proxy model emits the signal filterIncoming,
when the filtering is done it will emit the signal filterFinished. These signals are used to set delegates and
collapsed states in the view.

InstrumentTreeViewBase
^^^^^^^^^^^^^^^^^^^^^^

The view is in charge of displaying the model data. It uses the ProxyModel to filter and sort the items for it. The
main thing you need to implement for this class is its delegate. Delegates are classes in charge of create the
widgets that are shown for each row of the view. Usually they are the way we represent the information we want to
show and allows us to interact with it.

When creating your own delegate, you need to inherit from the class QStyledItemDelegate.
Other than the constructor the only class that your delegate should have implemented is the createEditor class.
This class is responsible to return an already created widget for a specific item.
If any signal needs to be connected from or to this widget, it should happen in the createEditor function.

Things to pay attention when implementing the constructor:
    * You can add any extra action that you want in the context menu here.
    * When calling the super, don't forget to pass the delegateColumns argument to the base model indicating
       what columns utilize delegates.
    * Don't forget to call the setItemDelegateForColumn for all the columns that utilize delegates.
    * Don't forget to end the constructor by calling the function setAllDelegatesPersistent,
        if not, the delegates will not be shown.

InstrumentDisplayBase
^^^^^^^^^^^^^^^^^^^^^

This is the class that brings everything together. It is the widget that should be added to a layout.
When calling the constructor you can pass any of the 4 previous classes to it to utilize your version of it, instead
of the base one.

All items connect their own signals with their own slots, but if any class needs to connect to a slot of a different
class, that happens in the connectSignal method If you need to implement any of your own signals, override this
method and after calling the super version of it, connect your signals.

To add more items to the toolbar for any extra functionality you can do so by overriding the makeToolbar method.

"""

from pprint import pprint
from typing import Optional, List, Dict

from instrumentserver import QtCore, QtGui, QtWidgets


class ItemBase(QtGui.QStandardItem):
    """
    Base item for instrument models.

    :param name: The name. This should include all of the submodules.
    :param star: indicates if the item is starred.
    :param trash: indicates if the item is trashed.
    :param showDelegate: If true, the delegate for that item will be shown.
    :param element: The object we want to store here, this can be a parameter or a method at the moment.
        If this is None, it means that the item is a submodule and should only be there to store the children.
    """

    def __init__(self, name, star=False, trash=False, showDelegate=True, element=None, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.name = name
        self.star = star
        self.trash = trash
        self.showDelegate = showDelegate
        self.element = element

        self.setText(self.name)


class InstrumentModelBase(QtGui.QStandardItemModel):
    """
    Base model used to display information of an instrument (like parameters or methods).

    In the constructor of the implemented model, you should specify how many columns it has and set the header labels

    If you are implementing the addChildTo function it is very important that you emit the newItem signal in the end.
    Delegates will not work properly unless you do so. This is because the integrated signal that Qt has, is emitted
    at the beginning of the insertion process and not in the end, not allowing the delegates to be properly set

    The attribute you are trying to display must be a dictionary.

    :param instrument: The instrument we are trying to show.
    :param attr: The string name of the dictionary of the items we want to show ("parameters", for example)
    :param customItem: The item class the model should use.
    """
    #: Signal(ItemBase)
    #: Gets emitted after a new item has been added. The user is in charge of emitting it in their implementation
    #: of addChildTo
    newItem = QtCore.Signal(object)

    #: Signal()
    #: Emitted when the model refreshes.
    modelRefreshed = QtCore.Signal()

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
        The argument for either submodules or the instrument itself.

        :param module: A proxy instrument from which we want to add all of its attributes and submodules.
            If `None`, self.instrument will be used.
        :param prefix: any submodule name that should be added before the name of a parameter.
        """
        if module is None:
            module = self.instrument

        for objectName, obj in getattr(module, self.attr).items():
            # addItem only requires fullName, everything else is going to be passed as args and kwargs to the item
            # constructor
            if prefix is not None:
                objectName = '.'.join([prefix, objectName])
            self.addItem(fullName=objectName, star=False, trash=False, element=obj)

        for submodName, submod in module.submodules.items():
            if prefix is not None:
                submodName = '.'.join([prefix, submodName])
            self.loadItems(submod, submodName)

    def refreshAll(self):
        """
        Removes all the rows from the model, updates the instrument and loads the model again.
        """
        self.removeRows(0, self.rowCount())
        self.instrument.update()
        self.loadItems()
        self.modelRefreshed.emit()

    def insertItemTo(self, parent, item):
        """
        This is the only function that actually inserts items into the model.
        Overload for models that utilize more columns. **Don't call directly**

        If you are using delegates, this function should emit the newItem signal
        """
        if parent == self:
            self.setItem(self.rowCount(), 0, item)
        else:
            parent.appendRow(item)

    def addItem(self, fullName, **kwargs):
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
                subModItem = self.itemClass(name=smName, star=False, trash=False, showDelegate=False, element=None)
                self.insertItemTo(parent, subModItem)
                parent = subModItem
            else:
                parent = items[0]

        newItem = self.itemClass(name=fullName, **kwargs)
        self.insertItemTo(parent, newItem)

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

    #: Signal()
    #: Emitted before a filter occurs
    filterIncoming = QtCore.Signal()

    #: Signal()
    #: Emitted after a filter has occurred.
    filterFinished = QtCore.Signal()

    def __init__(self, sourceModel: InstrumentModelBase, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.setSourceModel(sourceModel)
        self.setRecursiveFilteringEnabled(True)
        self.setDynamicSortFilter(True)

        self.star = False
        self.trash = False

        self.sort(0, QtCore.Qt.DescendingOrder)

    @QtCore.Slot(int, QtCore.Qt.SortOrder)
    def onSortingIndicatorChanged(self, index, sortingOrder):
        self.sort(index, sortingOrder)

    @QtCore.Slot()
    def onToggleStar(self):
        if self.star:
            self.star = False
        else:
            self.star = True

        # When the start status changes, trigger a sorting so that the star items move.
        if self.sortOrder() == QtCore.Qt.DescendingOrder:
            self.sort(0, QtCore.Qt.AscendingOrder)
            self.sort(0, QtCore.Qt.DescendingOrder)
        elif self.sortOrder() == QtCore.Qt.AscendingOrder:
            self.sort(0, QtCore.Qt.DescendingOrder)
            self.sort(0, QtCore.Qt.AscendingOrder)

    @QtCore.Slot()
    def onToggleTrash(self):
        if self.trash:
            self.trash = False
        else:
            self.trash = True
        self.triggerFiltering()

    @QtCore.Slot(str)
    def onTextFilterChange(self, filter: str):
        self.filterIncoming.emit()
        self.setFilterRegExp(filter)
        self.filterFinished.emit()

    def triggerFiltering(self):
        self.filterIncoming.emit()
        self.invalidateFilter()
        self.filterFinished.emit()

    def _isParentTrash(self, parent):
        """
        Recursive function to see if any parent of an item is trash.
        """
        if parent is None:
            return False

        if parent.trash:
            return True

        return self._isParentTrash(parent.parent())

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
                if hasattr(leftItem, 'star') and hasattr(rightItem, 'star'):
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

    def __init__(self, model, delegateColumns: Optional[List[int]]=None, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Indicates if a column is using delegates.
        self.delegateColumns = delegateColumns
        self.lastSelectedItem = None
        # Stores the last collapsed state before a change in filtering to restore it afterwards.
        # The keys are persistent indexes from the original model (not the proxy one) and the values a bool
        # indicating its collapsed state
        self.collapsedState: Dict[QtCore.QPersistentModelIndex, bool] = {}
        self.collapsedStateDebug: Dict[str, bool] = {}

        self.setModel(model)

        # Because we are filtering we set a proxy model as the model, however, there are times we want to work with
        # the real model
        self.modelActual: InstrumentModelBase = self.model().sourceModel()

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

    @QtCore.Slot()
    def fillCollapsedDict(self, parentItem: Optional[ItemBase]=None):
        """
        Fills the collapsed state dictionary to be recovered after a filter event occured.
        """
        if parentItem is None:
            for i in range(self.modelActual.rowCount()):
                index = self.modelActual.index(i, 0)
                item = self.modelActual.itemFromIndex(index)
                persistentIndex = QtCore.QPersistentModelIndex(index)
                proxyIndex = self.model().mapFromSource(index)
                if proxyIndex.isValid():
                    self.collapsedState[persistentIndex] = self.isExpanded(proxyIndex)
                    if item.hasChildren():
                        self.fillCollapsedDict(item)
        else:
            for i in range(parentItem.rowCount()):
                child = parentItem.child(i, 0)
                childIndex = self.modelActual.indexFromItem(child)
                persistentIndex = QtCore.QPersistentModelIndex(childIndex)
                proxyIndex = self.model().mapFromSource(childIndex)
                if proxyIndex.isValid():
                    self.collapsedState[persistentIndex] = self.isExpanded(proxyIndex)
                    if child.hasChildren():
                        self.fillCollapsedDict(child)

    @QtCore.Slot()
    def restoreCollapsedDict(self):
        """
        Goes through the collapsed state dictionary, and expands any item that should be expanded. It also resets
        the persistent editors and triggers a resizing of delegates.
        """
        for persistentIndex, state in self.collapsedState.items():
            modelIndex = self.modelActual.index(persistentIndex.row(), persistentIndex.column(), persistentIndex.parent())
            item = self.modelActual.itemFromIndex(modelIndex)
            proxyIndex = self.model().mapFromSource(modelIndex)
            self.setExpanded(proxyIndex, state)
            if item.showDelegate:
                delegateIndexes = [self.modelActual.index(persistentIndex.row(), x, persistentIndex.parent()) for x in
                                   self.delegateColumns]
                proxyDelegateIndexes = [self.model().mapFromSource(index) for index in delegateIndexes]
                for delegateIndex in proxyDelegateIndexes:
                    self.openPersistentEditor(delegateIndex)
        self.scheduleDelayedItemsLayout()

    def setAllDelegatesPersistent(self, parentIndex=None):
        """
        Recursive function that goes through the entire model and sets all delegates to be persistent editors

        :param parentIndex: If None, start the process. if it's an item, it will go through the children
        """
        if parentIndex is None:
            for i in range(self.model().rowCount()):
                for column in self.delegateColumns:
                    index = self.model().index(i, column)
                    index0 = self.model().index(i, 0)  # Only items at column 0 hold children and model info
                    item0 = self.modelActual.itemFromIndex(self.model().mapToSource(index0))
                    if item0.showDelegate:
                        self.openPersistentEditor(index)
                    if item0.hasChildren():
                        self.setAllDelegatesPersistent(index0)

        else:
            parentItem = self.modelActual.itemFromIndex(self.model().mapToSource(parentIndex))
            for i in range(parentItem.rowCount()):
                for column in self.delegateColumns:
                    item = parentItem.child(i, column)
                    item0 = parentItem.child(i, 0)
                    index = self.model().mapFromSource(self.modelActual.indexFromItem(item))
                    index0 = self.model().mapFromSource(self.modelActual.indexFromItem(item0))
                    if item0.showDelegate:
                        self.openPersistentEditor(index)
                    if item0.hasChildren():
                        self.setAllDelegatesPersistent(index0)

    @QtCore.Slot(object)
    def onCheckDelegate(self, item):
        """
        Makes sure that the delegates are shown if needed.

        :param item: The item whose row the delegates need to be activated
        """
        if item is not None:
            if item.showDelegate:
                row = item.row()
                parent = item.parent()
                for column in self.delegateColumns:
                    if parent is None:
                        sibling = self.modelActual.item(row, column)
                    else:
                        sibling = parent.child(row, column)
                    index = self.model().mapFromSource(self.modelActual.indexFromItem(sibling))
                    self.openPersistentEditor(index)
            self.scheduleDelayedItemsLayout()

    @QtCore.Slot(QtCore.QPoint)
    def onContextMenuRequested(self, pos):

        # We get the item from the real model, not the proxy model
        originalModel = self.model().sourceModel()
        proxyIndex = self.indexAt(pos)
        index = self.model().mapToSource(proxyIndex)

        # catch the case if the user rightcliks on any other column
        if index.column() != 0:
            parent = originalModel.itemFromIndex(index.parent())
            if parent is None:
                item = originalModel.item(index.row(), 0)
            else:
                item = parent.child(index.row(), 0)
        else:
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

    All the type variables, require the class type and not an initialized object of the variables.
    
    :param instrument: The instrument we want to display the attribute from.
    :param attr: string of the name of the dictionary we want to display, like 'parameters' or 'function'
    :param itemType: The type of item the model should use. 
    :param modelType: The type of model that should be used.
    :param proxyModelType: The type of proxy model that should be used.
    :param viewType: The type of view that should be used.
    """
    def __init__(self, instrument,
                 attr: str,
                 itemType = ItemBase,
                 modelType = InstrumentModelBase,
                 proxyModelType = InstrumentSortFilterProxyModel,
                 viewType = InstrumentTreeViewBase,
                 *args, **kwargs):
        super().__init__(*args, **kwargs)

        # initializing variables
        self.instrument = instrument
        self.attr = attr
        self.itemClass = itemType

        # initializing all the different classes
        self.model = modelType(instrument, attr, itemType, parent=self)
        self.proxyModel = proxyModelType(self.model)
        self.view = viewType(self.proxyModel)

        self.layout_ = QtWidgets.QVBoxLayout()

        self.toolBar, self.lineEdit = self.makeToolbar()
        self.layout_.addWidget(self.toolBar)

        self.layout_.addWidget(self.view)

        self.setLayout(self.layout_)

        self.view.expandAll()

        self.connectSignals()

    def connectSignals(self):
        """
        Connects all the signals to slots of different classes. Override to add more signals
        """
        self.model.newItem.connect(self.view.onCheckDelegate)
        self.model.modelRefreshed.connect(self.view.expandAll)

        self.proxyModel.filterIncoming.connect(self.view.fillCollapsedDict)
        self.proxyModel.filterFinished.connect(self.view.restoreCollapsedDict)

        self.view.itemStarToggle.connect(self.model.onItemStarToggle)
        self.view.itemTrashToggle.connect(self.model.onItemTrashToggle)

        self.lineEdit.textChanged.connect(self.proxyModel.onTextFilterChange)

        self.view.header().sortIndicatorChanged.connect(self.proxyModel.onSortingIndicatorChanged)

    def makeToolbar(self):
        """
        Creates the toolbar, override to add more buttons to the toolbar.
        """
        toolbar = QtWidgets.QToolBar(self)
        toolbar.setIconSize(QtCore.QSize(16, 16))

        refreshAction = toolbar.addAction(
            QtGui.QIcon(":/icons/refresh.svg"),
            "refresh all parameters from the instrument",
        )
        refreshAction.triggered.connect(lambda x: self.refreshAll())

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

    @QtCore.Slot()
    def refreshAll(self):
        self.model.refreshAll()

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

