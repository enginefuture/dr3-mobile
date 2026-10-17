#import "LauncherViewController.h"

static NSString *text(NSString *zh, NSString *en) {
    return [NSLocale.preferredLanguages.firstObject hasPrefix:@"zh"] ? zh : en;
}

@interface LauncherViewController () <UITableViewDataSource, UITableViewDelegate>
@property BOOL wideAvailable, lanAvailable, ready, starting;
@property (copy) NSString *reason;
@property (strong) UITableView *table;
@property (strong) UISegmentedControl *mode;
@property (strong) UISwitch *hud, *metalfx, *lan;
@property (strong) UIButton *play;
@end

@implementation LauncherViewController
- (instancetype)initWithWideAvailable:(BOOL)wide lanAvailable:(BOOL)lan ready:(BOOL)ready reason:(NSString *)reason {
    if((self=[super init])){_wideAvailable=wide;_lanAvailable=lan;_ready=ready;_reason=reason;}
    return self;
}
- (UILabel *)label:(NSString *)value style:(UIFontTextStyle)style color:(UIColor *)color {
    UILabel *l=[UILabel new];l.text=value;l.font=[UIFont preferredFontForTextStyle:style];
    l.adjustsFontForContentSizeCategory=YES;l.numberOfLines=0;l.textColor=color;return l;
}
- (void)viewDidLoad {
    [super viewDidLoad];
    // Match the project launcher reference: a Play action beside native settings.
    self.view.backgroundColor=UIColor.systemGroupedBackgroundColor;
    self.view.tintColor=UIColor.systemIndigoColor;
    NSUserDefaults *defaults=NSUserDefaults.standardUserDefaults;
    [defaults registerDefaults:@{@"LaunchWide":@YES,@"LaunchMetalHUD":@YES,@"LaunchMetalFX":@YES,@"LaunchLocalLAN":@YES}];
    self.mode=[[UISegmentedControl alloc] initWithItems:@[text(@"正常",@"Normal"),text(@"宽屏",@"Wide")]];
    self.mode.selectedSegmentIndex=self.wideAvailable&&[defaults boolForKey:@"LaunchWide"]?1:0;
    [self.mode setEnabled:self.wideAvailable forSegmentAtIndex:1];
    self.mode.accessibilityIdentifier=@"display-mode";
    [self.mode addTarget:self action:@selector(changed:) forControlEvents:UIControlEventValueChanged];
    self.hud=[UISwitch new];self.hud.on=[defaults boolForKey:@"LaunchMetalHUD"];
    self.hud.accessibilityIdentifier=@"metal-hud";self.hud.accessibilityLabel=@"Metal HUD";
    self.metalfx=[UISwitch new];self.metalfx.on=[defaults boolForKey:@"LaunchMetalFX"];
    self.metalfx.accessibilityIdentifier=@"metalfx";self.metalfx.accessibilityLabel=@"MetalFX";
    self.lan=[UISwitch new];self.lan.on=self.lanAvailable&&[defaults boolForKey:@"LaunchLocalLAN"];self.lan.enabled=self.lanAvailable;
    self.lan.accessibilityIdentifier=@"local-lan";self.lan.accessibilityLabel=text(@"本地 Wi-Fi 联机",@"Local Wi-Fi multiplayer");
    for(UISwitch *s in @[self.hud,self.metalfx,self.lan])[s addTarget:self action:@selector(changed:) forControlEvents:UIControlEventValueChanged];
    UILabel *title=[self label:@"DR3 Mobile" style:UIFontTextStyleLargeTitle color:UIColor.labelColor];
    title.accessibilityTraits|=UIAccessibilityTraitHeader;
    UILabel *subtitle=[self label:text(@"启动设置",@"Launch settings") style:UIFontTextStyleTitle3 color:UIColor.secondaryLabelColor];
    self.play=[UIButton buttonWithType:UIButtonTypeSystem];
    UIButtonConfiguration *c=[UIButtonConfiguration filledButtonConfiguration];
    c.title=text(@"开始游戏",@"Play");c.buttonSize=UIButtonConfigurationSizeLarge;
    self.play.configuration=c;self.play.enabled=self.ready;self.play.accessibilityIdentifier=@"start-game";
    [self.play addTarget:self action:@selector(start:) forControlEvents:UIControlEventTouchUpInside];
    UILabel *note=[self label:self.ready?text(@"设置会自动保存，下次打开可重新选择。",@"Settings are saved. Choose again whenever you reopen the app."):self.reason
                         style:UIFontTextStyleFootnote color:self.ready?UIColor.secondaryLabelColor:UIColor.labelColor];
    UILabel *owned=[self label:text(@"暗黑破坏神 III · 永恒之战版",@"Diablo III · Eternal Collection") style:UIFontTextStyleFootnote color:UIColor.secondaryLabelColor];
    UIStackView *intro=[[UIStackView alloc] initWithArrangedSubviews:@[title,subtitle,self.play,note,owned]];
    intro.axis=UILayoutConstraintAxisVertical;intro.spacing=16;
    [intro setCustomSpacing:8 afterView:title];[intro setCustomSpacing:24 afterView:subtitle];
    UIScrollView *left=[UIScrollView new];[left addSubview:intro];intro.translatesAutoresizingMaskIntoConstraints=NO;
    [NSLayoutConstraint activateConstraints:@[
        [intro.leadingAnchor constraintEqualToAnchor:left.contentLayoutGuide.leadingAnchor],
        [intro.trailingAnchor constraintEqualToAnchor:left.contentLayoutGuide.trailingAnchor],
        [intro.topAnchor constraintEqualToAnchor:left.contentLayoutGuide.topAnchor],
        [intro.bottomAnchor constraintEqualToAnchor:left.contentLayoutGuide.bottomAnchor],
        [intro.widthAnchor constraintEqualToAnchor:left.frameLayoutGuide.widthAnchor]]];
    self.table=[[UITableView alloc] initWithFrame:CGRectZero style:UITableViewStyleInsetGrouped];
    self.table.dataSource=self;self.table.delegate=self;self.table.rowHeight=UITableViewAutomaticDimension;
    self.table.estimatedRowHeight=56;self.table.contentInsetAdjustmentBehavior=UIScrollViewContentInsetAdjustmentNever;
    UIStackView *columns=[[UIStackView alloc] initWithArrangedSubviews:@[left,self.table]];
    columns.axis=UILayoutConstraintAxisHorizontal;columns.spacing=24;columns.translatesAutoresizingMaskIntoConstraints=NO;
    [self.view addSubview:columns];UILayoutGuide *safe=self.view.safeAreaLayoutGuide;
    [NSLayoutConstraint activateConstraints:@[
        [columns.leadingAnchor constraintEqualToAnchor:safe.leadingAnchor constant:24],
        [columns.trailingAnchor constraintEqualToAnchor:safe.trailingAnchor constant:-24],
        [columns.topAnchor constraintEqualToAnchor:safe.topAnchor constant:16],
        [columns.bottomAnchor constraintEqualToAnchor:safe.bottomAnchor constant:-16],
        [left.widthAnchor constraintEqualToAnchor:columns.widthAnchor multiplier:0.38],
        [self.play.heightAnchor constraintGreaterThanOrEqualToConstant:50],
        [self.mode.heightAnchor constraintGreaterThanOrEqualToConstant:44]]];
}
- (NSInteger)numberOfSectionsInTableView:(UITableView *)table {return 3;}
- (NSInteger)tableView:(UITableView *)table numberOfRowsInSection:(NSInteger)section {return section==1?2:1;}
- (NSString *)tableView:(UITableView *)table titleForHeaderInSection:(NSInteger)section {
    return section==0?text(@"画面模式",@"Display mode"):section==1?text(@"图形选项",@"Graphics"):text(@"局域网",@"Local network");
}
- (NSString *)tableView:(UITableView *)table titleForFooterInSection:(NSInteger)section {
    if(section==2)return self.lanAvailable?text(@"在同一 Wi-Fi 内使用游戏的本地联机入口。",@"Use the game’s local multiplayer mode on the same Wi-Fi network."):text(@"此构建未包含本地联机。",@"Local multiplayer is unavailable in this build.");
    if(section==1)return self.metalfx.on?text(@"720p 渲染，MetalFX 超分至 2K 输出。HUD 显示帧率与 GPU 数据。",@"Render at 720p and use MetalFX for 2K output. HUD shows frame rate and GPU data."):text(@"720p 渲染，直接适配屏幕。HUD 显示帧率与 GPU 数据。",@"Render at 720p and fit the display directly. HUD shows frame rate and GPU data.");
    if(!self.wideAvailable)return text(@"当前构建未包含宽屏模式。",@"This build does not include wide mode.");
    return self.mode.selectedSegmentIndex==1?
        text(@"扩大左右视野并适配 HUD；图形负载会增加。",@"Expand the horizontal view and adapt the HUD. Increases GPU load."):
        text(@"保留原版 16:9 画面，屏幕两侧可能留有黑边。",@"Keep the original 16:9 picture. Side margins may remain.");
}
- (UITableViewCell *)tableView:(UITableView *)table cellForRowAtIndexPath:(NSIndexPath *)path {
    UITableViewCell *cell=[[UITableViewCell alloc] initWithStyle:UITableViewCellStyleDefault reuseIdentifier:nil];
    cell.selectionStyle=UITableViewCellSelectionStyleNone;
    if(path.section==0){
        [cell.contentView addSubview:self.mode];self.mode.translatesAutoresizingMaskIntoConstraints=NO;
        [NSLayoutConstraint activateConstraints:@[
            [self.mode.leadingAnchor constraintEqualToAnchor:cell.contentView.layoutMarginsGuide.leadingAnchor],
            [self.mode.trailingAnchor constraintEqualToAnchor:cell.contentView.layoutMarginsGuide.trailingAnchor],
            [self.mode.topAnchor constraintEqualToAnchor:cell.contentView.topAnchor constant:8],
            [self.mode.bottomAnchor constraintEqualToAnchor:cell.contentView.bottomAnchor constant:-8]]];
    } else {
        UIListContentConfiguration *content=[cell defaultContentConfiguration];
        content.text=path.section==2?text(@"本地 Wi-Fi 联机",@"Local Wi-Fi multiplayer"):path.row==0?@"Metal HUD":text(@"MetalFX 超分",@"MetalFX upscaling");
        content.textProperties.numberOfLines=0;cell.contentConfiguration=content;
        cell.accessoryView=path.section==2?self.lan:path.row==0?self.hud:self.metalfx;
        [cell.heightAnchor constraintGreaterThanOrEqualToConstant:56].active=YES;
    }
    return cell;
}
- (void)changed:(id)sender {
    NSUserDefaults *d=NSUserDefaults.standardUserDefaults;
    [d setBool:self.mode.selectedSegmentIndex==1 forKey:@"LaunchWide"];
    [d setBool:self.hud.on forKey:@"LaunchMetalHUD"];
    [d setBool:self.metalfx.on forKey:@"LaunchMetalFX"];
    [d setBool:self.lan.on forKey:@"LaunchLocalLAN"];
    if(sender==self.mode||sender==self.metalfx)[self.table reloadData];
}
- (void)start:(UIButton *)sender {
    if(!self.ready||self.starting)return;
    self.starting=YES;sender.enabled=NO;[self changed:nil];
    if(self.onPlay)self.onPlay(self.mode.selectedSegmentIndex==1,self.hud.on,self.metalfx.on,self.lan.on);
    self.starting=NO;sender.enabled=self.ready;
}
- (BOOL)prefersStatusBarHidden {return YES;}
- (UIInterfaceOrientationMask)supportedInterfaceOrientations {return UIInterfaceOrientationMaskLandscape;}
@end
