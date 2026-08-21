#import <Cocoa/Cocoa.h>

@interface DropView : NSView
@property (copy) void (^filesDropped)(NSArray<NSURL *> *);
@end

@implementation DropView
- (instancetype)initWithFrame:(NSRect)frame {
    if ((self = [super initWithFrame:frame])) {
        [self registerForDraggedTypes:@[NSPasteboardTypeFileURL]];
        self.wantsLayer = YES;
        self.layer.backgroundColor = [[NSColor controlBackgroundColor] CGColor];
        self.layer.cornerRadius = 10;
        NSTextField *label = [NSTextField labelWithString:@"把一个或多个原始 MP4 拖到这里\n先严格检查，通过后才允许转换"];
        label.alignment = NSTextAlignmentCenter;
        label.font = [NSFont systemFontOfSize:15 weight:NSFontWeightMedium];
        label.textColor = NSColor.secondaryLabelColor;
        label.translatesAutoresizingMaskIntoConstraints = NO;
        [self addSubview:label];
        [NSLayoutConstraint activateConstraints:@[
            [label.centerXAnchor constraintEqualToAnchor:self.centerXAnchor],
            [label.centerYAnchor constraintEqualToAnchor:self.centerYAnchor]
        ]];
    }
    return self;
}
- (NSDragOperation)draggingEntered:(id<NSDraggingInfo>)sender { return NSDragOperationCopy; }
- (BOOL)performDragOperation:(id<NSDraggingInfo>)sender {
    NSArray *items = [[sender draggingPasteboard] readObjectsForClasses:@[[NSURL class]] options:@{NSPasteboardURLReadingFileURLsOnlyKey:@YES}];
    if (self.filesDropped) self.filesDropped(items); return YES;
}
@end

@interface AppDelegate : NSObject <NSApplicationDelegate, NSTableViewDataSource, NSTableViewDelegate>
@property NSWindow *window;
@property NSTextView *logView;
@property NSTextView *detailView;
@property NSTableView *fileTable;
@property NSProgressIndicator *progressIndicator;
@property NSButton *convertButton;
@property NSButton *hardwareButton;
@property NSButton *clearButton;
@property NSButton *chooseButton;
@property NSTextField *statusLabel;
@property NSTextField *footerLabel;
@property NSMutableArray<NSURL *> *accepted;
@property NSMutableSet<NSString *> *knownPaths;
@property NSMutableArray<NSMutableDictionary *> *fileRows;
@property NSUInteger pendingChecks;
@property NSUInteger rejectedChecks;
@property NSUInteger inspectionGeneration;
@property BOOL isConverting;
@property NSUInteger currentJobIndex;
@property NSUInteger currentJobTotal;
@property NSString *currentJobName;
@end

@implementation AppDelegate
- (void)applicationDidFinishLaunching:(NSNotification *)notification {
    self.accepted = [NSMutableArray array];
    self.knownPaths = [NSMutableSet set];
    self.fileRows = [NSMutableArray array];
    self.window = [[NSWindow alloc] initWithContentRect:NSMakeRect(0,0,1100,760)
        styleMask:NSWindowStyleMaskTitled|NSWindowStyleMaskClosable|NSWindowStyleMaskMiniaturizable|NSWindowStyleMaskResizable
        backing:NSBackingStoreBuffered defer:NO];
    self.window.minSize = NSMakeSize(940, 680);
    self.window.title = @"Vivo Lightroom 档案转换器";
    [self.window center];
    NSView *root = self.window.contentView;

    NSString *iconPath=[NSBundle.mainBundle pathForResource:@"AppIcon" ofType:@"icns"];
    NSImage *bundleIcon=iconPath ? [[NSImage alloc] initWithContentsOfFile:iconPath] : nil;
    if (bundleIcon) [NSApp setApplicationIconImage:bundleIcon];
    NSImageView *icon = [[NSImageView alloc] initWithFrame:NSZeroRect];
    icon.image = bundleIcon ?: NSApp.applicationIconImage;
    icon.imageScaling = NSImageScaleProportionallyUpOrDown;
    NSTextField *title = [NSTextField labelWithString:@"Vivo Lightroom 档案转换器"];
    title.font = [NSFont systemFontOfSize:24 weight:NSFontWeightSemibold];
    NSTextField *subtitle = [NSTextField labelWithString:@"严格核对输入结构，保留已验证元数据，不覆盖原片或已有输出。"];
    subtitle.textColor = NSColor.secondaryLabelColor;
    DropView *drop = [[DropView alloc] initWithFrame:NSZeroRect];
    self.chooseButton = [NSButton buttonWithTitle:@"选择视频…" target:self action:@selector(chooseFiles:)];
    self.convertButton = [NSButton buttonWithTitle:@"转换全部合格项" target:self action:@selector(convertAll:)];
    self.convertButton.enabled = NO;
    self.hardwareButton = [NSButton checkboxWithTitle:@"使用 VideoToolbox 硬件编码（实验，Q65）" target:self action:@selector(hardwareChanged:)];
    self.hardwareButton.toolTip = @"使用 Apple 硬件 HEVC 编码器；速度更快，但码流可能与已验证的 CPU 版本不同。";
    self.statusLabel = [NSTextField labelWithString:@"等待添加视频"];
    self.statusLabel.textColor = NSColor.secondaryLabelColor;
    self.statusLabel.font = [NSFont systemFontOfSize:13 weight:NSFontWeightMedium];
    self.progressIndicator = [[NSProgressIndicator alloc] initWithFrame:NSZeroRect];
    self.progressIndicator.style = NSProgressIndicatorStyleBar;
    self.progressIndicator.minValue = 0; self.progressIndicator.maxValue = 100;
    self.progressIndicator.indeterminate = NO; self.progressIndicator.doubleValue = 0; self.progressIndicator.hidden=YES;
    self.clearButton = [NSButton buttonWithTitle:@"清除" target:self action:@selector(clearLog:)];

    NSTextField *filesLabel = [NSTextField labelWithString:@"输入文件"];
    filesLabel.font = [NSFont systemFontOfSize:13 weight:NSFontWeightSemibold];
    NSScrollView *tableScroll = [[NSScrollView alloc] initWithFrame:NSZeroRect];
    tableScroll.hasVerticalScroller = YES; tableScroll.borderType = NSBezelBorder;
    self.fileTable = [[NSTableView alloc] initWithFrame:NSZeroRect];
    self.fileTable.dataSource = self; self.fileTable.delegate = self;
    self.fileTable.allowsMultipleSelection = NO;
    self.fileTable.rowHeight = 30;
    NSTableColumn *fileColumn = [[NSTableColumn alloc] initWithIdentifier:@"file"];
    fileColumn.title = @"文件"; fileColumn.width = 280; fileColumn.minWidth = 180;
    NSTableColumn *statusColumn = [[NSTableColumn alloc] initWithIdentifier:@"status"];
    statusColumn.title = @"状态"; statusColumn.width = 125; statusColumn.minWidth = 100;
    NSTableColumn *summaryColumn = [[NSTableColumn alloc] initWithIdentifier:@"summary"];
    summaryColumn.title = @"输入视频摘要"; summaryColumn.width = 620; summaryColumn.minWidth = 300;
    [self.fileTable addTableColumn:fileColumn]; [self.fileTable addTableColumn:statusColumn]; [self.fileTable addTableColumn:summaryColumn];
    tableScroll.documentView = self.fileTable;

    NSTextField *detailLabel = [NSTextField labelWithString:@"文件信息与校验项目"];
    detailLabel.font = [NSFont systemFontOfSize:13 weight:NSFontWeightSemibold];
    NSTextField *logLabel = [NSTextField labelWithString:@"实时运行日志"];
    logLabel.font = [NSFont systemFontOfSize:13 weight:NSFontWeightSemibold];
    NSScrollView *detailScroll = [[NSScrollView alloc] initWithFrame:NSZeroRect];
    NSScrollView *logScroll = [[NSScrollView alloc] initWithFrame:NSZeroRect];
    self.detailView = [self configuredTextViewForScroll:detailScroll monospaced:NO];
    self.logView = [self configuredTextViewForScroll:logScroll monospaced:YES];
    self.detailView.string = @"加入视频后，选择上方文件即可查看输入参数和每一项校验结果。";

    self.footerLabel = [NSTextField labelWithString:@"CPU输出：*_LR_CRF8_archive.mp4。provenance记录为x265 CRF 8。"];
    self.footerLabel.textColor = NSColor.secondaryLabelColor; self.footerLabel.font = [NSFont systemFontOfSize:11];
    NSArray *views = @[icon,title,subtitle,drop,self.chooseButton,self.convertButton,self.hardwareButton,self.statusLabel,self.progressIndicator,self.clearButton,filesLabel,tableScroll,detailLabel,logLabel,detailScroll,logScroll,self.footerLabel];
    for (NSView *v in views) { v.translatesAutoresizingMaskIntoConstraints = NO; [root addSubview:v]; }
    [NSLayoutConstraint activateConstraints:@[
        [icon.leadingAnchor constraintEqualToAnchor:root.leadingAnchor constant:18], [icon.topAnchor constraintEqualToAnchor:root.topAnchor constant:12],
        [icon.widthAnchor constraintEqualToConstant:52], [icon.heightAnchor constraintEqualToConstant:52],
        [title.leadingAnchor constraintEqualToAnchor:icon.trailingAnchor constant:12], [title.topAnchor constraintEqualToAnchor:root.topAnchor constant:14],
        [subtitle.leadingAnchor constraintEqualToAnchor:title.leadingAnchor], [subtitle.topAnchor constraintEqualToAnchor:title.bottomAnchor constant:3],
        [self.chooseButton.trailingAnchor constraintEqualToAnchor:root.trailingAnchor constant:-18], [self.chooseButton.centerYAnchor constraintEqualToAnchor:title.centerYAnchor],
        [self.convertButton.trailingAnchor constraintEqualToAnchor:self.chooseButton.leadingAnchor constant:-8], [self.convertButton.centerYAnchor constraintEqualToAnchor:self.chooseButton.centerYAnchor],
        [self.hardwareButton.trailingAnchor constraintEqualToAnchor:self.convertButton.leadingAnchor constant:-12], [self.hardwareButton.centerYAnchor constraintEqualToAnchor:self.chooseButton.centerYAnchor],
        [drop.leadingAnchor constraintEqualToAnchor:root.leadingAnchor constant:18], [drop.trailingAnchor constraintEqualToAnchor:root.trailingAnchor constant:-18],
        [drop.topAnchor constraintEqualToAnchor:icon.bottomAnchor constant:12], [drop.heightAnchor constraintEqualToConstant:82],
        [self.statusLabel.leadingAnchor constraintEqualToAnchor:drop.leadingAnchor], [self.statusLabel.topAnchor constraintEqualToAnchor:drop.bottomAnchor constant:9],
        [self.progressIndicator.leadingAnchor constraintEqualToAnchor:self.statusLabel.trailingAnchor constant:16], [self.progressIndicator.centerYAnchor constraintEqualToAnchor:self.statusLabel.centerYAnchor],
        [self.progressIndicator.widthAnchor constraintGreaterThanOrEqualToConstant:260],
        [self.progressIndicator.trailingAnchor constraintEqualToAnchor:self.clearButton.leadingAnchor constant:-14],
        [self.clearButton.trailingAnchor constraintEqualToAnchor:root.trailingAnchor constant:-18], [self.clearButton.topAnchor constraintEqualToAnchor:drop.bottomAnchor constant:10],
        [filesLabel.leadingAnchor constraintEqualToAnchor:root.leadingAnchor constant:18], [filesLabel.topAnchor constraintEqualToAnchor:self.statusLabel.bottomAnchor constant:12],
        [tableScroll.leadingAnchor constraintEqualToAnchor:root.leadingAnchor constant:18], [tableScroll.trailingAnchor constraintEqualToAnchor:root.trailingAnchor constant:-18],
        [tableScroll.topAnchor constraintEqualToAnchor:filesLabel.bottomAnchor constant:5], [tableScroll.heightAnchor constraintEqualToConstant:180],
        [detailLabel.leadingAnchor constraintEqualToAnchor:root.leadingAnchor constant:18], [detailLabel.topAnchor constraintEqualToAnchor:tableScroll.bottomAnchor constant:12],
        [logLabel.leadingAnchor constraintEqualToAnchor:root.centerXAnchor constant:7], [logLabel.centerYAnchor constraintEqualToAnchor:detailLabel.centerYAnchor],
        [detailScroll.leadingAnchor constraintEqualToAnchor:root.leadingAnchor constant:18], [detailScroll.trailingAnchor constraintEqualToAnchor:root.centerXAnchor constant:-7],
        [detailScroll.topAnchor constraintEqualToAnchor:detailLabel.bottomAnchor constant:5], [detailScroll.bottomAnchor constraintEqualToAnchor:self.footerLabel.topAnchor constant:-10],
        [logScroll.leadingAnchor constraintEqualToAnchor:root.centerXAnchor constant:7], [logScroll.trailingAnchor constraintEqualToAnchor:root.trailingAnchor constant:-18],
        [logScroll.topAnchor constraintEqualToAnchor:logLabel.bottomAnchor constant:5], [logScroll.bottomAnchor constraintEqualToAnchor:self.footerLabel.topAnchor constant:-10],
        [self.footerLabel.leadingAnchor constraintEqualToAnchor:root.leadingAnchor constant:18], [self.footerLabel.bottomAnchor constraintEqualToAnchor:root.bottomAnchor constant:-12]
    ]];
    __weak typeof(self) weakSelf = self;
    drop.filesDropped = ^(NSArray<NSURL *> *urls) { [weakSelf addFiles:urls]; };
    [self.window makeKeyAndOrderFront:nil];
    [NSApp activateIgnoringOtherApps:YES];
    NSString *dependencyProblem=[self dependencyProblem];
    if (dependencyProblem.length) {
        self.chooseButton.enabled=NO;
        self.convertButton.enabled=NO;
        self.statusLabel.stringValue=@"运行依赖尚未安装";
        self.detailView.string=[NSString stringWithFormat:@"无法开始检查或转换\n\n%@\n\n请运行随项目提供的 install_dependencies.command，然后重新打开App。",dependencyProblem];
        NSAlert *alert=[NSAlert new];
        alert.messageText=@"需要先安装运行依赖";
        alert.informativeText=[NSString stringWithFormat:@"%@\n\n运行 install_dependencies.command 后重新打开App。",dependencyProblem];
        [alert addButtonWithTitle:@"知道了"];
        [alert beginSheetModalForWindow:self.window completionHandler:nil];
    }
}

- (NSTextView *)configuredTextViewForScroll:(NSScrollView *)scroll monospaced:(BOOL)monospaced {
    scroll.hasVerticalScroller = YES; scroll.borderType = NSBezelBorder;
    NSTextView *view = [[NSTextView alloc] initWithFrame:scroll.contentView.bounds];
    view.editable = NO; view.selectable = YES;
    view.font = monospaced ? [NSFont monospacedSystemFontOfSize:11 weight:NSFontWeightRegular] : [NSFont systemFontOfSize:12];
    view.textColor = NSColor.labelColor; view.backgroundColor = NSColor.textBackgroundColor;
    view.minSize = NSMakeSize(0,0); view.maxSize = NSMakeSize(CGFLOAT_MAX,CGFLOAT_MAX);
    view.verticallyResizable = YES; view.horizontallyResizable = NO; view.autoresizingMask = NSViewWidthSizable;
    view.textContainer.containerSize = NSMakeSize(scroll.contentView.bounds.size.width,CGFLOAT_MAX);
    view.textContainer.widthTracksTextView = YES;
    view.textContainerInset = NSMakeSize(8,8);
    scroll.documentView = view;
    return view;
}

- (NSInteger)numberOfRowsInTableView:(NSTableView *)tableView { return self.fileRows.count; }
- (NSView *)tableView:(NSTableView *)tableView viewForTableColumn:(NSTableColumn *)column row:(NSInteger)rowIndex {
    NSMutableDictionary *row=self.fileRows[rowIndex];
    NSString *key=column.identifier;
    NSString *value=[row[key] isKindOfClass:NSString.class] ? row[key] : @"";
    NSTextField *field=[NSTextField labelWithString:value];
    field.lineBreakMode=NSLineBreakByTruncatingMiddle;
    field.font=[NSFont systemFontOfSize:12];
    field.toolTip=value;
    if ([key isEqualToString:@"file"]) field.font=[NSFont systemFontOfSize:12 weight:NSFontWeightMedium];
    if ([key isEqualToString:@"status"]) {
        if ([value containsString:@"通过"] || [value containsString:@"完成"]) field.textColor=NSColor.systemGreenColor;
        else if ([value containsString:@"拒绝"] || [value containsString:@"失败"]) field.textColor=NSColor.systemRedColor;
        else if ([value containsString:@"检查"] || [value containsString:@"转换"]) field.textColor=NSColor.systemBlueColor;
    }
    return field;
}
- (void)tableViewSelectionDidChange:(NSNotification *)notification { [self showSelectedFileDetails]; }
- (NSMutableDictionary *)rowForURL:(NSURL *)url {
    NSString *path=url.URLByStandardizingPath.path;
    for (NSMutableDictionary *row in self.fileRows) if ([row[@"path"] isEqualToString:path]) return row;
    return nil;
}
- (NSString *)summaryForInspection:(NSDictionary *)j {
    NSString *size=[NSByteCountFormatter stringFromByteCount:[j[@"size_bytes"] longLongValue] countStyle:NSByteCountFormatterCountStyleFile];
    return [NSString stringWithFormat:@"%@×%@ · %.3f fps · %@帧 · %.3f秒 · %@ · %@ · EIS %@包",
        j[@"width"] ?: @"?",j[@"height"] ?: @"?",[j[@"fps"] doubleValue],j[@"frame_count"] ?: @"?",
        [j[@"duration"] doubleValue],size,j[@"video_profile"] ?: @"?",j[@"eis_packets"] ?: @"?"];
}
- (void)showSelectedFileDetails {
    NSInteger index=self.fileTable.selectedRow;
    if (index<0 || index>=self.fileRows.count) {
        self.detailView.string=@"选择一个输入文件以查看完整信息与校验清单。"; return;
    }
    NSDictionary *row=self.fileRows[index]; NSDictionary *j=row[@"inspection"];
    if (![j isKindOfClass:NSDictionary.class]) {
        self.detailView.string=[NSString stringWithFormat:@"%@\n\n路径\n%@\n\n状态\n%@",row[@"file"],row[@"path"],row[@"status"]]; return;
    }
    NSString *(^value)(id)=^NSString *(id object) {
        return (!object || object==NSNull.null || ![[object description] length]) ? @"未提供" : [object description];
    };
    NSString *size=[NSByteCountFormatter stringFromByteCount:[j[@"size_bytes"] longLongValue] countStyle:NSByteCountFormatterCountStyleFile];
    NSMutableString *text=[NSMutableString string];
    [text appendFormat:@"输入文件\n%@\n\n完整路径\n%@\n\n",j[@"name"] ?: @"?",j[@"path"] ?: @"?"];
    [text appendFormat:@"视频\n%@×%@ · %.6f fps · %@帧 · %.3f秒 · %@\n%@ / %@ / %@\n\n",
        j[@"width"] ?: @"?",j[@"height"] ?: @"?",[j[@"fps"] doubleValue],j[@"frame_count"] ?: @"?",
        [j[@"duration"] doubleValue],size,j[@"video_codec"] ?: @"?",j[@"video_profile"] ?: @"?",j[@"pixel_format"] ?: @"?"];
    [text appendFormat:@"音频与附加数据\n%@\n%@ · EIS %@包\n\n",value(j[@"audio_description"]),value(j[@"dolby_vision"]),value(j[@"eis_packets"])];
    [text appendFormat:@"拍摄信息\n设备：%@\n时间：%@\nGPS：%@\n\n校验清单\n",value(j[@"device"]),value(j[@"creation_time"]),value(j[@"location"])];
    for (NSDictionary *check in j[@"checks"] ?: @[]) {
        NSString *state=check[@"state"];
        NSString *symbol=[state isEqualToString:@"passed"] ? @"✓" : ([state isEqualToString:@"failed"] ? @"✗" : @"—");
        [text appendFormat:@"%@ %@\n   %@\n",symbol,check[@"name"] ?: @"未命名项目",check[@"detail"] ?: @""];
    }
    if ([j[@"reasons"] count]) [text appendFormat:@"\n拒绝原因\n%@",[j[@"reasons"] componentsJoinedByString:@"\n"]];
    NSDictionary *verification=row[@"verification"];
    if ([verification isKindOfClass:NSDictionary.class]) {
        [text appendFormat:@"\n\n转换结果\n✓ 输出文件已完成全部复检\n%@\n%@\n",
            verification[@"mode"] ?: @"", verification[@"path"] ?: @""];
        [text appendString:@"视频参数与方向 · 帧数与PTS · AAC逐包哈希 · EIS逐包哈希\nDolby Vision配置与RPU · 单时间层 · 完整解码 · 元数据与来源记录"];
    }
    self.detailView.string=text;
}
- (void)reloadRowForURL:(NSURL *)url {
    [self.fileTable reloadData];
    if (self.fileTable.selectedRow<0 && self.fileRows.count) [self.fileTable selectRowIndexes:[NSIndexSet indexSetWithIndex:0] byExtendingSelection:NO];
    [self showSelectedFileDetails];
}
- (void)handleProgressChunk:(NSString *)chunk {
    for (NSString *line in [chunk componentsSeparatedByCharactersInSet:NSCharacterSet.newlineCharacterSet]) {
        if (![line hasPrefix:@"PROGRESS\t"]) continue;
        NSArray *parts=[line componentsSeparatedByString:@"\t"];
        if (parts.count<3) continue;
        double value=[parts[1] doubleValue]*100.0; NSString *stage=parts[2];
        dispatch_async(dispatch_get_main_queue(), ^{
            self.progressIndicator.hidden=NO; self.progressIndicator.indeterminate=NO; [self.progressIndicator stopAnimation:nil]; self.progressIndicator.doubleValue=value;
            self.statusLabel.stringValue=[NSString stringWithFormat:@"正在转换 %lu/%lu：%@ — %@",(unsigned long)self.currentJobIndex,(unsigned long)self.currentJobTotal,self.currentJobName ?: @"",stage];
        });
    }
    for (NSString *line in [chunk componentsSeparatedByCharactersInSet:NSCharacterSet.newlineCharacterSet]) {
        if (![line hasPrefix:@"VERIFY\tPASS\t"]) continue;
        NSArray *parts=[line componentsSeparatedByString:@"\t"];
        if (parts.count<3) continue;
        NSString *item=parts[2];
        dispatch_async(dispatch_get_main_queue(), ^{
            self.statusLabel.stringValue=[NSString stringWithFormat:@"正在复检 %lu/%lu：%@ — %@",(unsigned long)self.currentJobIndex,(unsigned long)self.currentJobTotal,self.currentJobName ?: @"",item];
        });
    }
}

- (NSString *)pythonPath {
    NSString *support=[NSHomeDirectory() stringByAppendingPathComponent:@"Library/Application Support/VivoLightroomArchiveConverter/venv/bin/python3"];
    for (NSString *p in @[support,@"/opt/homebrew/bin/python3.12",@"/usr/local/bin/python3.12",@"/Library/Frameworks/Python.framework/Versions/3.12/bin/python3"])
        if ([[NSFileManager defaultManager] isExecutableFileAtPath:p]) return p;
    return nil;
}
- (NSString *)enginePath { return [[NSBundle mainBundle] pathForResource:@"converter_engine" ofType:@"py" inDirectory:@"Engine"]; }
- (NSString *)toolPath:(NSString *)name {
    for (NSString *prefix in @[@"/opt/homebrew/bin",@"/usr/local/bin",@"/usr/bin",@"/bin"]) {
        NSString *path=[prefix stringByAppendingPathComponent:name];
        if ([[NSFileManager defaultManager] isExecutableFileAtPath:path]) return path;
    }
    return nil;
}
- (NSString *)dependencyProblem {
    NSMutableArray<NSString *> *missing=[NSMutableArray array];
    NSString *python=self.pythonPath;
    if (!python) [missing addObject:@"Python 3.12 与专用虚拟环境"];
    else {
        NSTask *task=[NSTask new]; task.executableURL=[NSURL fileURLWithPath:python];
        task.arguments=@[@"-c",@"import av; assert av.__version__ == '18.1.0'"];
        task.standardOutput=[NSPipe pipe]; task.standardError=[NSPipe pipe];
        NSError *error=nil;
        if (![task launchAndReturnError:&error]) [missing addObject:@"PyAV 18.1.0"];
        else { [task waitUntilExit]; if (task.terminationStatus!=0) [missing addObject:@"PyAV 18.1.0"] ; }
    }
    if (![self toolPath:@"ffmpeg"] || ![self toolPath:@"ffprobe"]) [missing addObject:@"FFmpeg / ffprobe"];
    if (![self toolPath:@"dovi_tool"]) [missing addObject:@"dovi_tool"];
    return missing.count ? [@"缺少：" stringByAppendingString:[missing componentsJoinedByString:@"、"]] : nil;
}
- (NSDictionary *)environment {
    NSMutableDictionary *e = [NSMutableDictionary dictionaryWithDictionary:NSProcessInfo.processInfo.environment];
    e[@"VAC_RESOURCE_DIR"] = NSBundle.mainBundle.resourcePath;
    e[@"PATH"] = @"/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin";
    e[@"PYTHONDONTWRITEBYTECODE"] = @"1";
    return e;
}
- (void)append:(NSString *)text {
    [self appendRaw:[text stringByAppendingString:@"\n"]];
}
- (void)appendRaw:(NSString *)text {
    dispatch_async(dispatch_get_main_queue(), ^{
        NSDictionary *attributes = @{
            NSForegroundColorAttributeName: NSColor.labelColor,
            NSFontAttributeName: [NSFont monospacedSystemFontOfSize:12 weight:NSFontWeightRegular]
        };
        NSAttributedString *line = [[NSAttributedString alloc] initWithString:text attributes:attributes];
        [self.logView.textStorage appendAttributedString:line];
        [self.logView scrollRangeToVisible:NSMakeRange(self.logView.string.length,0)];
    });
}
- (void)updateInspectionStatus {
    NSAssert(NSThread.isMainThread, @"UI state must be updated on the main thread");
    NSUInteger accepted = self.accepted.count;
    if (self.pendingChecks > 0) {
        self.progressIndicator.hidden=NO;
        self.progressIndicator.indeterminate=YES; [self.progressIndicator startAnimation:nil];
        self.statusLabel.stringValue = [NSString stringWithFormat:@"正在检查 %lu 个；已通过 %lu 个，拒绝 %lu 个",
            (unsigned long)self.pendingChecks, (unsigned long)accepted, (unsigned long)self.rejectedChecks];
    } else if (accepted || self.rejectedChecks) {
        if (!self.isConverting) { [self.progressIndicator stopAnimation:nil]; self.progressIndicator.indeterminate=NO; self.progressIndicator.doubleValue=0; self.progressIndicator.hidden=YES; }
        self.statusLabel.stringValue = [NSString stringWithFormat:@"检查完成：%lu 个通过，%lu 个拒绝",
            (unsigned long)accepted, (unsigned long)self.rejectedChecks];
    } else {
        [self.progressIndicator stopAnimation:nil]; self.progressIndicator.indeterminate=NO; self.progressIndicator.doubleValue=0; self.progressIndicator.hidden=YES;
        self.statusLabel.stringValue = @"等待添加视频";
    }
    self.convertButton.enabled = (!self.isConverting && self.pendingChecks == 0 && accepted > 0);
}
- (void)hardwareChanged:(id)sender {
    if (self.hardwareButton.state == NSControlStateValueOn) {
        self.footerLabel.stringValue = @"硬件输出：*_LR_VT_Q65_archive.mp4。provenance记录为Apple VideoToolbox Q65。";
    } else {
        self.footerLabel.stringValue = @"CPU输出：*_LR_CRF8_archive.mp4。provenance记录为x265 CRF 8。";
    }
}
- (NSDictionary *)runEngine:(NSArray<NSString *> *)args text:(NSString **)text error:(NSString **)error {
    NSString *python=self.pythonPath;
    if (!python) { if (error) *error=@"未找到Python 3.12运行环境"; return nil; }
    NSTask *task = [[NSTask alloc] init]; task.executableURL = [NSURL fileURLWithPath:python];
    task.arguments = [@[[self enginePath]] arrayByAddingObjectsFromArray:args]; task.environment = self.environment;
    NSPipe *out = [NSPipe pipe], *err = [NSPipe pipe]; task.standardOutput=out; task.standardError=err;
    [task launchAndReturnError:nil]; [task waitUntilExit];
    NSData *od=[out.fileHandleForReading readDataToEndOfFile], *ed=[err.fileHandleForReading readDataToEndOfFile];
    if (text) *text=[[NSString alloc] initWithData:od encoding:NSUTF8StringEncoding];
    if (error) *error=[[NSString alloc] initWithData:ed encoding:NSUTF8StringEncoding];
    if (task.terminationStatus!=0) return nil;
    return [NSJSONSerialization JSONObjectWithData:od options:0 error:nil];
}
- (BOOL)runConversion:(NSURL *)url hardware:(BOOL)hardware error:(NSString **)error {
    NSString *python=self.pythonPath;
    if (!python) { if (error) *error=@"未找到Python 3.12运行环境"; return NO; }
    NSTask *task = [[NSTask alloc] init];
    task.executableURL = [NSURL fileURLWithPath:python];
    NSMutableArray *args = [NSMutableArray arrayWithObjects:[self enginePath], @"convert", url.path, nil];
    if (hardware) [args addObject:@"hardware"];
    task.arguments = args; task.environment = self.environment;
    NSPipe *out = [NSPipe pipe], *err = [NSPipe pipe]; task.standardOutput=out; task.standardError=err;
    out.fileHandleForReading.readabilityHandler = ^(NSFileHandle *handle) {
        NSData *data = handle.availableData;
        if (data.length) {
            NSString *chunk = [[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding];
            if (chunk.length) { [self handleProgressChunk:chunk]; [self appendRaw:chunk]; }
        }
    };
    NSError *launchError=nil;
    if (![task launchAndReturnError:&launchError]) {
        out.fileHandleForReading.readabilityHandler=nil;
        if (error) *error=launchError.localizedDescription;
        return NO;
    }
    [task waitUntilExit];
    out.fileHandleForReading.readabilityHandler=nil;
    NSData *tail=[out.fileHandleForReading readDataToEndOfFile];
    if (tail.length) {
        NSString *chunk=[[NSString alloc] initWithData:tail encoding:NSUTF8StringEncoding];
        if (chunk.length) { [self handleProgressChunk:chunk]; [self appendRaw:chunk]; }
    }
    NSData *ed=[err.fileHandleForReading readDataToEndOfFile];
    if (error) *error=[[NSString alloc] initWithData:ed encoding:NSUTF8StringEncoding];
    return task.terminationStatus==0;
}
- (void)addFiles:(NSArray<NSURL *> *)urls {
    NSAssert(NSThread.isMainThread, @"addFiles must run on the main thread");
    if (self.isConverting) { [self append:@"转换进行中，暂不接受新文件。"] ; return; }
    NSMutableArray<NSURL *> *fresh = [NSMutableArray array];
    for (NSURL *url in urls) {
        NSString *path = url.URLByStandardizingPath.path;
        if ([self.knownPaths containsObject:path]) {
            [self append:[NSString stringWithFormat:@"跳过重复文件：%@", path]];
            continue;
        }
        [self.knownPaths addObject:path];
        NSURL *standardURL=url.URLByStandardizingPath;
        [fresh addObject:standardURL];
        NSDictionary *attrs=[NSFileManager.defaultManager attributesOfItemAtPath:path error:nil];
        NSString *size=[NSByteCountFormatter stringFromByteCount:[attrs[NSFileSize] longLongValue] countStyle:NSByteCountFormatterCountStyleFile];
        [self.fileRows addObject:[@{@"url":standardURL,@"path":path,@"file":standardURL.lastPathComponent,@"status":@"等待检查",@"summary":[NSString stringWithFormat:@"%@ · 等待读取媒体信息",size]} mutableCopy]];
    }
    if (fresh.count == 0) {
        [self updateInspectionStatus];
        return;
    }
    self.pendingChecks += fresh.count;
    NSUInteger generation = self.inspectionGeneration;
    [self.fileTable reloadData];
    if (self.fileTable.selectedRow<0 && self.fileRows.count) [self.fileTable selectRowIndexes:[NSIndexSet indexSetWithIndex:0] byExtendingSelection:NO];
    [self showSelectedFileDetails];
    [self updateInspectionStatus];
    for (NSURL *url in fresh) {
        NSMutableDictionary *initialRow=[self rowForURL:url]; initialRow[@"status"]=@"正在检查";
        [self.fileTable reloadData];
        [self append:[NSString stringWithFormat:@"\n检查：%@",url.path]];
        dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED,0), ^{
            NSString *out=nil,*err=nil; NSDictionary *j=[self runEngine:@[@"inspect",url.path] text:&out error:&err];
            dispatch_async(dispatch_get_main_queue(), ^{
                if (generation != self.inspectionGeneration) return;
                if (self.pendingChecks > 0) self.pendingChecks--;
                NSMutableDictionary *row=[self rowForURL:url];
                if (!j) {
                    self.rejectedChecks++;
                    row[@"status"]=@"检查失败"; row[@"summary"]=err ?: @"未知错误";
                    [self append:[@"检查失败：" stringByAppendingString:err ?: @"未知错误"]];
                } else if ([j[@"accepted"] boolValue]) {
                    if (![self.accepted containsObject:url]) [self.accepted addObject:url];
                    row[@"status"]=@"检查通过"; row[@"summary"]=[self summaryForInspection:j]; row[@"inspection"]=j;
                    [self append:[NSString stringWithFormat:@"✓ 通过 | %@×%@ | %@帧 | %.3ffps | %.3f秒 | %@ | EIS %@包\n  设备：%@  GPS：%@  时间：%@",
                        j[@"width"],j[@"height"],j[@"frame_count"],[j[@"fps"] doubleValue],[j[@"duration"] doubleValue],j[@"dolby_vision"],j[@"eis_packets"],j[@"device"],j[@"location"],j[@"creation_time"]]];
                } else {
                    self.rejectedChecks++;
                    row[@"status"]=@"拒绝转换"; row[@"summary"]=[self summaryForInspection:j]; row[@"inspection"]=j;
                    [self append:[NSString stringWithFormat:@"✗ 拒绝转换：%@\n  %@",url.lastPathComponent,[j[@"reasons"] componentsJoinedByString:@"\n  "]]];
                }
                [self reloadRowForURL:url];
                [self updateInspectionStatus];
            });
        });
    }
}
- (void)chooseFiles:(id)sender {
    NSOpenPanel *p=[NSOpenPanel openPanel];p.allowsMultipleSelection=YES;p.canChooseDirectories=NO;
    if ([p runModal]==NSModalResponseOK) [self addFiles:p.URLs];
}
- (void)convertAll:(id)sender {
    if (self.pendingChecks > 0 || self.accepted.count == 0) return;
    self.convertButton.enabled=NO;
    self.clearButton.enabled=NO;
    self.hardwareButton.enabled=NO;
    self.chooseButton.enabled=NO;
    self.isConverting=YES;
    self.progressIndicator.hidden=NO; self.progressIndicator.indeterminate=NO; self.progressIndicator.doubleValue=0;
    BOOL useHardware = (self.hardwareButton.state == NSControlStateValueOn);
    NSArray *jobs; @synchronized(self.accepted) { jobs=[self.accepted copy]; }
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED,0), ^{
        __block NSUInteger succeeded=0, failed=0, index=0;
        for (NSURL *url in jobs) {
            index++;
            NSUInteger currentIndex=index;
            dispatch_sync(dispatch_get_main_queue(), ^{
                self.currentJobIndex=currentIndex; self.currentJobTotal=jobs.count; self.currentJobName=url.lastPathComponent;
                self.statusLabel.stringValue=[NSString stringWithFormat:@"正在转换 %lu/%lu：%@",(unsigned long)currentIndex,(unsigned long)jobs.count,url.lastPathComponent];
                self.progressIndicator.doubleValue=0;
                NSMutableDictionary *row=[self rowForURL:url]; row[@"status"]=@"正在转换"; [self reloadRowForURL:url];
            });
            [self append:[NSString stringWithFormat:@"\n开始转换：%@",url.lastPathComponent]];
            NSString *err=nil; BOOL ok=[self runConversion:url hardware:useHardware error:&err];
            if (!ok) { failed++; [self append:[@"转换失败：" stringByAppendingString:err.length ? err : @"未知错误"]]; }
            else succeeded++;
            dispatch_sync(dispatch_get_main_queue(), ^{
                NSMutableDictionary *row=[self rowForURL:url];
                if (ok) {
                    NSString *suffix=useHardware ? @"_LR_VT_Q65_archive.mp4" : @"_LR_CRF8_archive.mp4";
                    NSString *outputPath=[[url.path stringByDeletingPathExtension] stringByAppendingString:suffix];
                    row[@"status"]=@"完成并通过复检";
                    row[@"summary"]=[NSString stringWithFormat:@"%@ · 输出复检通过",row[@"summary"] ?: @""];
                    row[@"verification"]=@{@"path":outputPath,@"mode":useHardware ? @"VideoToolbox Q65" : @"x265 CRF 8"};
                } else row[@"status"]=@"转换失败";
                [self reloadRowForURL:url];
            });
        }
        [self append:@"\n批量任务结束。"];
        dispatch_async(dispatch_get_main_queue(), ^{
            self.clearButton.enabled=YES;
            self.hardwareButton.enabled=YES;
            self.chooseButton.enabled=YES;
            self.isConverting=NO;
            self.progressIndicator.indeterminate=NO; self.progressIndicator.doubleValue=100; self.progressIndicator.hidden=YES;
            self.statusLabel.stringValue=[NSString stringWithFormat:@"批量完成：%lu 个成功并通过复检，%lu 个失败",(unsigned long)succeeded,(unsigned long)failed];
        });
    });
}
- (void)clearLog:(id)sender {
    self.inspectionGeneration++;
    self.pendingChecks=0;
    self.rejectedChecks=0;
    self.logView.string=@"";
    self.detailView.string=@"加入视频后，选择上方文件即可查看输入参数和每一项校验结果。";
    [self.accepted removeAllObjects];
    [self.knownPaths removeAllObjects];
    [self.fileRows removeAllObjects]; [self.fileTable reloadData];
    [self updateInspectionStatus];
}
- (BOOL)applicationShouldTerminateAfterLastWindowClosed:(NSApplication *)sender { return YES; }
@end

int main(int argc,const char *argv[]) {
    @autoreleasepool { NSApplication *app=[NSApplication sharedApplication]; AppDelegate *d=[AppDelegate new]; app.delegate=d; [app run]; }
    return 0;
}
