#pragma once
#include <winrt/Windows.UI.Xaml.Media.Imaging.h>
#include <winrt/Windows.Storage.Streams.h>

static void BF_ProbePump() { MSG msg;while(PeekMessageW(&msg,nullptr,0,0,PM_REMOVE)){TranslateMessage(&msg);DispatchMessageW(&msg);} }

static void BF_SaveLayoutBitmap(const FrameworkElement& root,const std::filesystem::path& path) {
    Media::Imaging::RenderTargetBitmap bitmap;
    auto render=bitmap.RenderAsync(root);
    const auto until=GetTickCount64()+2000;
    while(render.Status()==wf::AsyncStatus::Started && GetTickCount64()<until) {BF_ProbePump();Sleep(1);}
    if(render.Status()!=wf::AsyncStatus::Completed) return;
    auto operation=bitmap.GetPixelsAsync();
    while(operation.Status()==wf::AsyncStatus::Started && GetTickCount64()<until) {BF_ProbePump();Sleep(1);}
    if(operation.Status()!=wf::AsyncStatus::Completed) return;
    auto buffer=operation.GetResults();
    auto reader=winrt::Windows::Storage::Streams::DataReader::FromBuffer(buffer);
    std::vector<uint8_t> pixels(buffer.Length());reader.ReadBytes(pixels);
    BITMAPFILEHEADER file{};file.bfType=0x4D42;file.bfOffBits=sizeof(file)+sizeof(BITMAPINFOHEADER);file.bfSize=file.bfOffBits+pixels.size();
    BITMAPINFOHEADER header{};header.biSize=sizeof(header);header.biWidth=bitmap.PixelWidth();header.biHeight=-bitmap.PixelHeight();
    header.biPlanes=1;header.biBitCount=32;header.biSizeImage=pixels.size();
    std::ofstream image(path,std::ios::binary);image.write(reinterpret_cast<char*>(&file),sizeof(file));
    image.write(reinterpret_cast<char*>(&header),sizeof(header));image.write(reinterpret_cast<char*>(pixels.data()),pixels.size());
}

// Recreate the classic Shell's independent content roots, inherited view model,
// nested account/power controls, and differently sized native item containers.
// The 63-DIP header margin, 32-DIP root padding, 52-DIP items-panel margin and
// pager column reproduce the structures in this machine's Windows PRI templates.
static bool BF_ProbeStartLayout(const std::filesystem::path& output) {
    auto trace=[&](const char* step){std::ofstream file(output/L"start-layout-stage.txt",std::ios::app);file<<step<<"\n";};
    trace("create");
    const bool observed=BF_Setting(L"probe_observer_layout")==L"1";
    if (observed) bf_is_start_menu=true;
    if (observed) {
        WNDCLASSW type{};type.lpfnWndProc=DefWindowProcW;type.hInstance=GetModuleHandleW(nullptr);
        type.lpszClassName=L"Windows.UI.Core.CoreWindow";RegisterClassW(&type);
    }
    HWND window=CreateWindowExW(0,observed?L"Windows.UI.Core.CoreWindow":L"STATIC",L"Start layout regression",WS_POPUP,30,30,760,850,nullptr,nullptr,GetModuleHandleW(nullptr),nullptr);
    Hosting::DesktopWindowXamlSource source;
    auto native=source.as<IDesktopWindowXamlSourceNative>();winrt::check_hresult(native->AttachToWindow(window));
    HWND child=nullptr;native->get_WindowHandle(&child);SetWindowPos(child,nullptr,0,0,760,850,SWP_NOZORDER|SWP_SHOWWINDOW);
    auto root=Markup::XamlReader::Load(LR"(<Grid xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation" xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml" Name="RootContent" Width="563" Height="625" Background="#FFEAF3F9">
      <VisualStateManager.VisualStateGroups><VisualStateGroup x:Name="ContentStates"><VisualState x:Name="Undocked">
        <Storyboard><DoubleAnimationUsingKeyFrames Storyboard.TargetName="AllAppsRoot" Storyboard.TargetProperty="Opacity">
            <DiscreteDoubleKeyFrame KeyTime="0" Value="1"/><LinearDoubleKeyFrame KeyTime="0:0:0.06" Value="0"/>
        </DoubleAnimationUsingKeyFrames><ObjectAnimationUsingKeyFrames Storyboard.TargetName="AllAppsRoot" Storyboard.TargetProperty="Visibility">
            <DiscreteObjectKeyFrame KeyTime="0:0:0.08" Value="Collapsed"/>
        </ObjectAnimationUsingKeyFrames></Storyboard>
      </VisualState></VisualStateGroup></VisualStateManager.VisualStateGroups>
      <Grid Name="NativeInnerContent" Margin="32,58,32,60">
        <Grid Name="AllAppsRoot" Width="282" Margin="0,-37,0,0">
          <Grid.RenderTransform><CompositeTransform TranslateX="-165"/></Grid.RenderTransform>
          <Grid.RowDefinitions><RowDefinition Height="40"/><RowDefinition/></Grid.RowDefinitions>
          <Grid Name="AllAppsPaneHeader" Margin="63,0,64,0">
            <Grid Margin="0,-3,12,0"><TextBlock Name="AllAppsHeading" Text="全部" Margin="16,8,0,8" FontSize="16"/></Grid>
          </Grid>
          <ListView Grid.Row="1" Name="AppsList" Margin="28,0,0,0" Padding="16,0,0,0">
            <ListView.ItemsPanel><ItemsPanelTemplate><Grid Margin="52,0,52,0">
              <Grid.ColumnDefinitions><ColumnDefinition Width="52"/><ColumnDefinition/><ColumnDefinition Width="52"/></Grid.ColumnDefinitions>
              <Grid.RowDefinitions><RowDefinition Height="40"/><RowDefinition Height="40"/><RowDefinition Height="40"/><RowDefinition Height="40"/><RowDefinition Height="40"/><RowDefinition Height="40"/><RowDefinition Height="40"/><RowDefinition Height="40"/></Grid.RowDefinitions>
            </Grid></ItemsPanelTemplate></ListView.ItemsPanel>
          </ListView>
        </Grid>
        <Grid Name="UndockedRoot" Width="308" Margin="116,-37,-116,0">
          <Grid Name="FrameRoot">
            <Grid Name="TopLevelRoot">
              <Grid.RowDefinitions><RowDefinition Height="40"/><RowDefinition/></Grid.RowDefinitions>
              <Grid Margin="63,-3,12,0" VerticalAlignment="Center">
                <TextBlock Name="PinnedListHeaderText" Text="已固定" Margin="16,8,0,8" FontSize="16"/>
              </Grid>
              <ContentControl Name="StartMenuPinnedList" Grid.Row="1" Margin="0,3,0,0" HorizontalContentAlignment="Stretch" VerticalContentAlignment="Stretch">
                <ContentControl.Template><ControlTemplate TargetType="ContentControl">
                  <Grid Name="Root" Padding="32,0,4,0">
                    <Grid.ColumnDefinitions><ColumnDefinition/><ColumnDefinition Width="24"/></Grid.ColumnDefinitions>
                    <GridView Name="PinnedList" Padding="0" HorizontalAlignment="Center" SelectionMode="Single">
                      <GridView.ItemsPanel><ItemsPanelTemplate><ItemsWrapGrid Orientation="Horizontal" ItemWidth="76" ItemHeight="76" MaximumRowsOrColumns="3"/></ItemsPanelTemplate></GridView.ItemsPanel>
                    </GridView>
                    <Border Name="PinnedListPipsPager" Grid.Column="1" Width="4" Height="20" Background="#607D8B" HorizontalAlignment="Center" VerticalAlignment="Center"/>
                  </Grid>
                </ControlTemplate></ContentControl.Template>
              </ContentControl>
            </Grid>
          </Grid>
        </Grid>
      </Grid>
      <Grid Name="NavigationPane" Width="543" Height="56" VerticalAlignment="Bottom">
        <Grid Name="RootPanel" FlowDirection="RightToLeft">
          <Grid.ColumnDefinitions><ColumnDefinition/><ColumnDefinition Width="Auto"/><ColumnDefinition Width="Auto"/></Grid.ColumnDefinitions>
          <Grid Name="UserTileView" Width="190"><Button Name="UserTileButton" Content="示例账户" Width="125" Height="36"/></Grid>
          <Grid Name="PowerButton" Grid.Column="2" Width="506" Margin="-506,0,0,0"><Button Name="PowerCommand" Width="36" Height="36" Padding="0" Background="Transparent"><FontIcon Glyph="&#xE7E8;" FontSize="18"/></Button></Grid>
          <ListView Name="NavigationPanePlacesListView" Grid.Column="1" Width="40" Padding="0" VerticalContentAlignment="Center"><ListViewItem Width="40" Height="40" Padding="0" VerticalContentAlignment="Center"><FontIcon Glyph="&#xE713;" FontSize="18"/></ListViewItem></ListView>
        </Grid>
      </Grid>
    </Grid>)").as<Controls::Grid>();
    BF_FindLayoutElement(root,L"StartMenuPinnedList").as<Controls::Control>().ApplyTemplate();
    auto apps=BF_FindLayoutElement(root,L"AppsList").as<Controls::ListViewBase>();
    const bool coreApps=BF_Setting(L"probe_core_apps")==L"1";
    const bool outerInset=BF_Setting(L"probe_outer_inset")==L"1";
    if (coreApps) {
        auto parent=BF_FindLayoutElement(root,L"AllAppsRoot").as<Controls::Grid>();
        Controls::GridView grid;grid.Name(L"AllAppsGrid");grid.Margin(apps.Margin());grid.Padding(apps.Padding());
        Controls::Grid::SetRow(grid,1);
        grid.ItemsPanel(Markup::XamlReader::Load(LR"(<ItemsPanelTemplate xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"><ItemsWrapGrid Orientation="Horizontal" MaximumRowsOrColumns="1" ItemWidth="536" Margin="52,0,52,0"/></ItemsPanelTemplate>)").as<Controls::ItemsPanelTemplate>());
        unsigned index=0;parent.Children().IndexOf(apps,index);parent.Children().RemoveAt(index);parent.Children().InsertAt(index,grid);apps=grid;
    }
    if (outerInset) {
        auto parent=BF_FindLayoutElement(root,L"AllAppsRoot").as<Controls::Grid>();
        auto wrapper=Markup::XamlReader::Load(LR"(<Grid xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation" Name="NativeViewportSlots">
            <Grid.ColumnDefinitions><ColumnDefinition Width="52"/><ColumnDefinition/><ColumnDefinition Width="52"/></Grid.ColumnDefinitions>
            <Border Grid.Column="2" IsHitTestVisible="False"/>
        </Grid>)").as<Controls::Grid>();
        unsigned index=0;parent.Children().IndexOf(apps,index);parent.Children().RemoveAt(index);
        Controls::Grid::SetRow(wrapper,1);Controls::Grid::SetRow(apps,0);Controls::Grid::SetColumn(apps,1);
        wrapper.Children().Append(apps);parent.Children().InsertAt(index,wrapper);
        apps.ItemsPanel(Markup::XamlReader::Load(LR"(<ItemsPanelTemplate xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"><ItemsStackPanel/></ItemsPanelTemplate>)").as<Controls::ItemsPanelTemplate>());
    }
    for (auto text:{L"A",L"应用列表：长名称显示测试",L"B",L"本地文件与文件夹",L"C",L"日历",L"图片",L"音乐"}) {
        auto item=coreApps?Controls::GridViewItem().as<Controls::ContentControl>():Controls::ListViewItem().as<Controls::ContentControl>();
        item.HorizontalContentAlignment(HorizontalAlignment::Stretch);item.Padding({});
        item.Background(Media::SolidColorBrush(winrt::Windows::UI::Color{}));
        if (wcslen(text)==1) {
            auto button=Markup::XamlReader::Load(LR"(<Button xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation" Name="Header" Padding="10,0,0,0" BorderThickness="0" HorizontalContentAlignment="Left">
              <Button.Template><ControlTemplate TargetType="Button"><Border Padding="{TemplateBinding Padding}"><TextBlock Name="Text" Text="{TemplateBinding Content}"/></Border></ControlTemplate></Button.Template>
            </Button>)").as<Controls::Button>();
            button.Content(winrt::box_value(text));item.Content(button);
        } else {
            Controls::StackPanel line;line.Orientation(Controls::Orientation::Horizontal);line.Margin({8,0,0,0});
            Controls::Border logo;logo.Name(L"AppListItemLogo");logo.Width(24);logo.Height(24);
            Controls::TextBlock label;label.Text(text);line.Children().Append(logo);line.Children().Append(label);item.Content(line);
        }
        apps.Items().Append(item);
    }
    auto pinned=BF_FindLayoutElement(root,L"PinnedList").as<Controls::GridView>();
    std::vector<Controls::GridViewItem> tiles;
    for (int i=0;i<15;++i) {
        Controls::GridViewItem item;item.MinWidth(96);item.MinHeight(96);item.Padding({8,8,8,8});
        item.Template(Markup::XamlReader::Load(LR"(<ControlTemplate xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation" TargetType="GridViewItem"><Border Name="ContentBorder" Background="Transparent"><Grid><ContentPresenter Name="ContentPresenter" Content="{TemplateBinding Content}"/></Grid></Border></ControlTemplate>)").as<Controls::ControlTemplate>());
        auto tile=Markup::XamlReader::Load(LR"(<Grid xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation" Name="NativeTileContent" Width="96" Height="84"><StackPanel HorizontalAlignment="Center" VerticalAlignment="Center">
            <Border Name="LogoContainer" Width="28" Height="28" Background="#487D9E" CornerRadius="6" HorizontalAlignment="Center"/>
            <TextBlock Name="DisplayName" Text="应用" Margin="0,6,0,0" HorizontalAlignment="Center"/>
        </StackPanel></Grid>)").as<Controls::Grid>();
        item.Content(tile);pinned.Items().Append(item);tiles.push_back(item);
    }
    auto originalParent=BF_FindLayoutElement(root,L"NativeInnerContent").as<Controls::Grid>();
    auto vm=winrt::box_value(L"native-view-model");originalParent.DataContext(vm);
    auto appsRoot=BF_FindLayoutElement(root,L"AllAppsRoot");auto pinnedRoot=BF_FindLayoutElement(root,L"UndockedRoot");
    auto footer=BF_FindLayoutElement(root,L"RootPanel").as<Controls::Grid>();
    const bool dark=BF_Setting(L"bigfish_theme")==L"Dark";
    root.Background(Media::SolidColorBrush(dark?winrt::Windows::UI::Color{255,35,44,52}:winrt::Windows::UI::Color{255,234,243,249}));
    unsigned detached=0;
    auto watchApps=appsRoot.Unloaded(winrt::auto_revoke,[&](auto&&,auto&&){++detached;});
    auto watchPinned=pinnedRoot.Unloaded(winrt::auto_revoke,[&](auto&&,auto&&){++detached;});
    // Reboot: a tree may be observed before it has loaded. Register layout work
    // now, but do not mutate it during construction or detach native template parts.
    BF_ArrangeStartColumns(root);
    trace("cold_registered");
    const bool deferred=appsRoot.Margin().Top==-37&&appsRoot.Width()==282;
    BF_ClearStartColumns();
    source.Content(root);ShowWindow(window,SW_SHOW);BF_ProbePump();root.UpdateLayout();
    // A private panel's ArrangeOverride can reserve 52 DIPs on both sides even
    // though its public Margin and Padding have both been cleared. Reproduce
    // that slot geometry with Grid columns instead of another removable margin.
    if (!coreApps) for (unsigned i=0;i<apps.Items().Size();++i) {
        auto item=apps.ContainerFromIndex(i).as<FrameworkElement>();
        Controls::Grid::SetColumn(item,1);Controls::Grid::SetRow(item,i);
    }
    root.UpdateLayout();
    auto hitAt=[&](const FrameworkElement& expected,wf::Point point) {
        const auto host=root.TransformToVisual(nullptr).TransformPoint(point);
        for (auto hit:Media::VisualTreeHelper::FindElementsInHostCoordinates(host,root))
            for (DependencyObject element=hit;element;element=Media::VisualTreeHelper::GetParent(element))
                if (element==expected) return true;
        return false;
    };
    trace("loaded");
    // Preserve the failure geometry as an explicit regression precondition.
    auto before=BF_FooterBounds(appsRoot,root);
    const bool oldOverflow=before.X<16;
    const bool oldTileOverflow=tiles[0].ActualWidth()>76;
    if (!observed) BF_ArrangeStartColumns(root);
    BF_AddStartSearchButton(footer);
    trace("arranged");
    root.UpdateLayout();BF_ProbePump();
    trace("layout");
    if (observed) {
        MH_Initialize();
        if (!Wh_ModInit() || MH_EnableHook(MH_ALL_HOOKS)!=MH_OK) throw std::runtime_error("observer hooks");
        BF_RequestShellInitialization(window);
        for (auto until=GetTickCount64()+600;GetTickCount64()<until;) {BF_ProbePump();Sleep(1);}
        trace("observer_attached");
    }
    std::vector<FrameworkElement> styled;
    auto collect=[&](auto&& self,const FrameworkElement& element)->void {
        styled.push_back(element);
        const int count=Media::VisualTreeHelper::GetChildrenCount(element);
        for(int i=0;i<count;++i) if(auto child=Media::VisualTreeHelper::GetChild(element,i).try_as<FrameworkElement>()) self(self,child);
    };
    collect(collect,root);
    if (!observed) for(unsigned i=0;i<styled.size();++i) ApplyCustomizations(static_cast<ElementId>(10000+i),styled[i],winrt::get_class_name(styled[i]).c_str());
    BF_ProbePump();root.UpdateLayout();BF_ProbePump();root.UpdateLayout();
    trace("styled");
    // Opening/closing moves both the whole page and its internal viewport.
    // Exercise real nonzero visual offsets while layout runs, including the
    // thousands of DIPs reported by the failing build. They must never turn
    // into layout margins or invalidate the list on every pass.
    bool stableDuringMotion=true;
    if (outerInset) {
        const auto viewport=BF_FindLayoutElement(root,L"NativeViewportSlots");
        Media::CompositeTransform pageMotion,viewMotion;
        originalParent.RenderTransform(pageMotion);
        viewport.RenderTransform(viewMotion);
        const auto appMargin=appsRoot.Margin(),pinMargin=pinnedRoot.Margin(),listMargin=apps.Margin();
        const double listWidth=apps.ActualWidth();
        for (double x : {563.0,-563.0,4496.0,0.0,563.0,0.0}) {
            pageMotion.TranslateX(x);
            viewMotion.TranslateX(-x/2);
            root.InvalidateArrange();root.UpdateLayout();BF_ProbePump();
            stableDuringMotion=stableDuringMotion && appsRoot.Margin()==appMargin &&
                pinnedRoot.Margin()==pinMargin && apps.Margin()==listMargin &&
                std::abs(apps.ActualWidth()-listWidth)<1;
        }
        originalParent.ClearValue(UIElement::RenderTransformProperty());
        viewport.ClearValue(UIElement::RenderTransformProperty());
        root.UpdateLayout();
    }
    // The real Shell reopens/closes both roots through CompositeTransform paths.
    // A static render never exercised these and missed the incompatible replacement.
    bool nativeAnimation=true;
    for (auto target:{appsRoot,pinnedRoot}) {
        try {
            Media::Animation::Storyboard storyboard;
            Media::Animation::DoubleAnimation animation;
            animation.EnableDependentAnimation(true);animation.From(0.0);animation.To(0.0);
            animation.Duration({wf::TimeSpan{10000},DurationType::TimeSpan});
            Media::Animation::Storyboard::SetTarget(animation,target);
            Media::Animation::Storyboard::SetTargetProperty(animation,L"(UIElement.RenderTransform).(CompositeTransform.TranslateY)");
            storyboard.Children().Append(animation);storyboard.Begin();BF_ProbePump();storyboard.Stop();
        } catch (const winrt::hresult_error&) {nativeAnimation=false;}
    }
    // Native Loaded/SizeChanged handlers may reapply their original inset after
    // initial styling. Also cover a build whose collection has a different name.
    const auto appsName=apps.Name();apps.Name(L"NativeAppsCollection");
    apps.ItemsPanelRoot().Margin({52,0,52,0});
    auto pinnedTemplate=Media::VisualTreeHelper::GetParent(pinned).as<Controls::Grid>();
    pinnedTemplate.Padding({32,0,4,0});
    auto appsPresenter=Media::VisualTreeHelper::GetParent(apps.ItemsPanelRoot()).try_as<Controls::ItemsPresenter>();
    if (appsPresenter) appsPresenter.Padding({16,0,16,0});
    root.UpdateLayout();BF_ProbePump();root.UpdateLayout();BF_ProbePump();root.UpdateLayout();
    const bool lateInsets=pinnedTemplate.Padding().Left==0 &&
        (!appsPresenter || appsPresenter.Padding().Left==0);
    apps.Name(appsName);
    const auto left=BF_FooterBounds(appsRoot,root),right=BF_FooterBounds(pinnedRoot,root);
    auto heading=BF_FindLayoutElement(root,L"AllAppsHeading").as<Controls::TextBlock>();
    const auto firstHeading=BF_FooterBounds(heading,root);
    const auto secondHeading=BF_FooterBounds(BF_FindLayoutElement(root,L"PinnedListHeaderText"),root);
    auto pageSwitch=VisualStateManager::GetVisualStateGroups(root).GetAt(0).States().GetAt(0).Storyboard();
    pageSwitch.Begin();
    for (auto until=GetTickCount64()+130;GetTickCount64()<until;) {BF_ProbePump();Sleep(1);}
    const bool bothColumnsVisible=appsRoot.Visibility()==Visibility::Visible && appsRoot.Opacity()>.99;
    pageSwitch.Stop();
    auto nextVm=winrt::box_value(L"updated-native-view-model");originalParent.DataContext(nextVm);
    bool hierarchy=detached==0&&Media::VisualTreeHelper::GetParent(appsRoot)==originalParent&&
        Media::VisualTreeHelper::GetParent(pinnedRoot)==originalParent&&appsRoot.DataContext()==nextVm&&pinnedRoot.DataContext()==nextVm;
    const auto appsBox=BF_FooterBounds(apps,root);
    const auto appsItemsBox=BF_FooterBounds(apps.ItemsPanelRoot(),root);
    const auto appItem=apps.ContainerFromIndex(1).as<FrameworkElement>();
    const auto appItemBox=BF_FooterBounds(appItem,root);
    const auto appLogo=BF_FooterBounds(BF_FindLayoutElement(apps.ContainerFromIndex(1).as<FrameworkElement>(),L"AppListItemLogo"),root);
    const auto letter=BF_FooterBounds(BF_FindLayoutElement(apps.ContainerFromIndex(0).as<FrameworkElement>(),L"Text"),root);
    const auto headingInk=firstHeading.X+heading.Padding().Left;
    const bool inkAligned=std::abs(headingInk-appLogo.X)<1 && std::abs(letter.X-appLogo.X)<1;
    const bool rowEdgesHit=hitAt(appItem,{left.X+2,appItemBox.Y+appItemBox.Height/2})&&
        hitAt(appItem,{left.X+left.Width-2,appItemBox.Y+appItemBox.Height/2});
    bool columns=std::abs(left.X-18)<1 && std::abs(right.X-left.X-left.Width-10)<1 &&
        std::abs(right.X+right.Width-root.ActualWidth()+10)<1 &&
        std::abs(firstHeading.Y-secondHeading.Y)<1 && std::abs(firstHeading.X-appsBox.X)<1 &&
        secondHeading.X>=right.X-1 && std::abs(appItemBox.X-firstHeading.X)<1 && inkAligned && hierarchy &&
        std::abs(appItemBox.Width-left.Width)<1&&appItemBox.X+appItemBox.Width<=right.X-9&&rowEdgesHit;
    bool hitboxes=true;
    std::vector<wf::Rect> bounds;
    double iconError=0,labelError=0;
    for(auto item:tiles) {
        auto box=BF_FooterBounds(item,root),icon=BF_FooterBounds(BF_FindLayoutElement(item,L"LogoContainer"),root);
        const auto label=BF_FooterBounds(BF_FindLayoutElement(item,L"DisplayName"),root);
        iconError=std::max<double>(iconError,std::abs(icon.X+icon.Width/2-box.X-box.Width/2));
        labelError=std::max<double>(labelError,std::abs(label.X+label.Width/2-box.X-box.Width/2));
        hitboxes=hitboxes && std::abs(label.X+label.Width/2-box.X-box.Width/2)<1;
        hitboxes=hitboxes&&std::abs(box.Width-76)<1&&std::abs(box.Height-84)<1&&
            std::abs(icon.Width-28)<1&&std::abs(icon.Height-28)<1&&
            std::abs((icon.X+icon.Width/2)-(box.X+box.Width/2))<1&&box.X>=right.X&&box.X+box.Width<=right.X+right.Width+1;
        for(auto previous:bounds) if (std::min(box.X+box.Width,previous.X+previous.Width)-std::max(box.X,previous.X)>.5 &&
                                     std::min(box.Y+box.Height,previous.Y+previous.Height)-std::max(box.Y,previous.Y)>.5) hitboxes=false;
        bounds.push_back(box);
    }
    hitboxes=hitboxes&&std::abs(bounds[0].X-right.X)<1&&
        std::abs(bounds[3].Y-bounds[0].Y)<1&&std::abs(bounds[4].X-bounds[0].X)<1&&
        std::abs(bounds[4].Y-bounds[0].Y-84)<1;
    const auto pinHeading=BF_FindLayoutElement(root,L"PinnedListHeaderText").as<Controls::TextBlock>();
    const auto headingAlignment=static_cast<int>(pinHeading.TextAlignment());
    hitboxes=hitboxes && std::abs(secondHeading.X+secondHeading.Width/2-bounds[0].X-bounds[0].Width/2)<1;
    const bool pinnedEdgeHit=hitAt(tiles[3],{bounds[3].X+bounds[3].Width-2,bounds[3].Y+bounds[3].Height/2});
    hitboxes=hitboxes&&pinnedEdgeHit;
    auto search=BF_FindLayoutElement(footer,L"BigFishNativeSearchButton");
    auto user=BF_FindLayoutElement(footer,L"UserTileButton");auto power=BF_FindLayoutElement(footer,L"PowerCommand");
    auto searchBox=BF_FooterBounds(search,root),userBox=BF_FooterBounds(user,root),powerBox=BF_FooterBounds(power,root);
    auto settingsList=BF_FindLayoutElement(footer,L"NavigationPanePlacesListView").as<Controls::ListView>();
    auto settingsItem=settingsList.ContainerFromIndex(0).as<Controls::ListViewItem>();
    auto settingsBox=BF_FooterBounds(settingsItem,root);
    auto settingsIcon=BF_FooterBounds(settingsItem.Content().as<FrameworkElement>(),root);
    const bool footerFits=search.Visibility()==Visibility::Visible&&searchBox.X>powerBox.X+powerBox.Width&&
        powerBox.X>=userBox.X+userBox.Width&&std::abs(searchBox.Y+searchBox.Height/2-userBox.Y-userBox.Height/2)<1&&bf_search_button_ready;
    const bool settingsCentered=std::abs(settingsIcon.X+settingsIcon.Width/2-settingsBox.X-settingsBox.Width/2)<1&&
        std::abs(settingsIcon.Y+settingsIcon.Height/2-searchBox.Y-searchBox.Height/2)<1&&settingsBox.X+settingsBox.Width<=root.ActualWidth()-9;
    pinned.SelectedIndex(4);root.UpdateLayout();
    for(auto until=GetTickCount64()+250;GetTickCount64()<until;) {BF_ProbePump();Sleep(1);}
    BF_SaveLayoutBitmap(root,output/L"start-layout.bmp");
    // Invoke only owned dummy controls: no system shutdown/logoff command exists
    // in this process. Check the routed Click and secondary-menu action as well
    // as geometry, so a visually correct but inert footer cannot pass.
    unsigned powerClicks=0,menuClicks=0;
    auto powerButton=power.as<Controls::Button>();
    auto clicked=powerButton.Click(winrt::auto_revoke,[&](auto&&,auto&&){++powerClicks;});
    auto powerPeer=BF_PanelPeer::CreatePeerForElement(powerButton);
    powerPeer.GetPattern(winrt::Windows::UI::Xaml::Automation::Peers::PatternInterface::Invoke)
        .as<winrt::Windows::UI::Xaml::Automation::Provider::IInvokeProvider>().Invoke();
    BF_ProbePump();
    Controls::MenuFlyout flyout;Controls::MenuFlyoutItem command;command.Text(L"测试操作");
    auto commandClicked=command.Click(winrt::auto_revoke,[&](auto&&,auto&&){++menuClicks;});
    flyout.Items().Append(command);flyout.ShowAt(powerButton);BF_ProbePump();root.UpdateLayout();
    auto menuPeer=BF_PanelPeer::CreatePeerForElement(command);
    menuPeer.GetPattern(winrt::Windows::UI::Xaml::Automation::Peers::PatternInterface::Invoke)
        .as<winrt::Windows::UI::Xaml::Automation::Provider::IInvokeProvider>().Invoke();
    BF_ProbePump();flyout.Hide();
    const bool commands=powerClicks==1&&menuClicks==1&&detached==0;
    // Expanded folders inherit the same pinned column and four-column cells.
    // Reproduce the obsolete fixed widths and negative inner offsets first.
    auto folder=Markup::XamlReader::Load(LR"(<ContentControl xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation" Name="ExpandedFolderList" Width="400" Height="480" Margin="85,40,0,0" HorizontalAlignment="Left" VerticalAlignment="Top">
      <ContentControl.Template><ControlTemplate TargetType="ContentControl">
        <Grid Name="FolderRoot">
          <Grid.ColumnDefinitions><ColumnDefinition/><ColumnDefinition Width="450"/><ColumnDefinition/></Grid.ColumnDefinitions>
          <Grid.RowDefinitions><RowDefinition/><RowDefinition Height="Auto"/><RowDefinition/></Grid.RowDefinitions>
          <Border Name="FolderSurface" Grid.Row="1" Grid.Column="1" Width="325" Margin="-40,0,40,0" Background="White"/>
           <Grid Name="FolderContent" Grid.Row="1" Grid.Column="1" Width="350" Margin="-85,0,0,0" Padding="32,32,4,32">
            <Grid.RowDefinitions><RowDefinition Height="48"/><RowDefinition/></Grid.RowDefinitions>
            <Grid.ColumnDefinitions><ColumnDefinition/><ColumnDefinition Width="24"/></Grid.ColumnDefinitions>
            <TextBox Name="ExpandedFolderNameTextBox" Grid.ColumnSpan="2" Text="编辑名称" MinWidth="350" FontSize="24"/>
            <GridView Name="FolderList" Grid.Row="1" Padding="0" SelectionMode="Single">
              <GridView.ItemsPanel><ItemsPanelTemplate><ItemsWrapGrid Orientation="Horizontal" ItemWidth="96" ItemHeight="96" MaximumRowsOrColumns="3"/></ItemsPanelTemplate></GridView.ItemsPanel>
            </GridView>
            <Border Grid.Row="1" Grid.Column="1" Width="4" Height="20" Background="#607D8B" HorizontalAlignment="Center" VerticalAlignment="Center"/>
          </Grid>
        </Grid>
      </ControlTemplate></ContentControl.Template>
    </ContentControl>)").as<Controls::ContentControl>();
    pinnedRoot.as<Controls::Grid>().Children().Append(folder);root.UpdateLayout();BF_ProbePump();
    auto folderList=BF_FindLayoutElement(folder,L"FolderList").as<Controls::GridView>();
    std::vector<Controls::GridViewItem> folderItems;
    for (unsigned i=0;i<6;++i) {
        Controls::GridViewItem item;item.MinWidth(96);item.MinHeight(96);item.Padding({8,8,8,8});
        Controls::StackPanel tile;tile.HorizontalAlignment(HorizontalAlignment::Center);
        Controls::Border icon;icon.Width(28);icon.Height(28);icon.CornerRadius({6,6,6,6});
        icon.Background(Media::SolidColorBrush(winrt::Windows::UI::Color{255,72,125,158}));
        Controls::TextBlock name;name.Text(L"应用 "+std::to_wstring(i+1));name.Margin({0,6,0,0});
        tile.Children().Append(icon);tile.Children().Append(name);item.Content(tile);
        folderList.Items().Append(item);folderItems.push_back(item);
    }
    root.UpdateLayout();BF_ProbePump();
    const auto oldFolder=BF_FooterBounds(folder,root);
    const bool folderOverflow=oldFolder.X+oldFolder.Width>right.X+right.Width+1;
    const auto folderStart=styled.size();collect(collect,folder);
    if (!observed) for(unsigned i=folderStart;i<styled.size();++i) ApplyCustomizations(static_cast<ElementId>(10000+i),styled[i],winrt::get_class_name(styled[i]).c_str());
    BF_ProbePump();root.UpdateLayout();BF_ProbePump();root.UpdateLayout();
    const auto folderBox=BF_FooterBounds(folder,root);
    auto folderSurface=BF_FindLayoutElement(folder,L"FolderSurface").as<Controls::Border>();
    auto folderTitle=BF_FindLayoutElement(folder,L"ExpandedFolderNameTextBox").as<Controls::TextBox>();
    const auto surfaceBox=BF_FooterBounds(folderSurface,root),titleBox=BF_FooterBounds(folderTitle,root);
    // With the real observer, creation already applies the folder rules. Only
    // the direct-style fixture can measure the unstyled overflow beforehand.
    bool folderFits=(observed||folderOverflow)&&std::abs(folderBox.X-right.X)<1&&std::abs(folderBox.Width-right.Width)<1&&
        surfaceBox.X>=right.X-1&&surfaceBox.X+surfaceBox.Width<=right.X+right.Width+1&&
        titleBox.X>=right.X&&titleBox.X+titleBox.Width<=right.X+right.Width+1&&root.Width()==563&&root.Height()==625;
    std::vector<wf::Rect> folderBoxes;
    for(auto item:folderItems) {
        auto box=BF_FooterBounds(item,root);
        auto icon=item.Content().as<Controls::StackPanel>().Children().GetAt(0).as<FrameworkElement>();
        folderFits=folderFits&&std::abs(box.Width-76)<1&&std::abs(box.Height-84)<1&&icon.Width()==28&&icon.Height()==28&&
            box.X>=right.X-.5&&box.X+box.Width<=right.X+right.Width+.5;
        folderBoxes.push_back(box);
    }
    folderFits=folderFits&&std::abs(folderBoxes[3].Y-folderBoxes[0].Y)<1&&
        std::abs(folderBoxes[4].X-folderBoxes[0].X)<1&&std::abs(folderBoxes[4].Y-folderBoxes[0].Y-84)<1;
    const auto folderInk=folderTitle.Foreground().try_as<Media::SolidColorBrush>();
    const bool folderAppearance=folderSurface.CornerRadius().TopLeft==18&&folderInk&&folderInk.Color().R==(dark?255:0);
    const bool folderEdgeHit=hitAt(folderSurface,{surfaceBox.X+surfaceBox.Width-4,surfaceBox.Y+surfaceBox.Height/2})&&
        hitAt(folderItems[3],{folderBoxes[3].X+folderBoxes[3].Width-2,folderBoxes[3].Y+folderBoxes[3].Height/2});
    folderFits=folderFits&&folderEdgeHit;
    // GridView's native entrance transition runs on the compositor. Capture
    // its settled appearance rather than a transparent, translated first frame.
    for(auto until=GetTickCount64()+350;GetTickCount64()<until;) {BF_ProbePump();Sleep(1);}
    BF_SaveLayoutBitmap(root,output/L"start-folder-layout.bmp");
    // A wider scrolling canvas can place the native vertical thumb on top of
    // the first pin even when the app rows themselves are correctly aligned.
    Controls::Grid barColumn;barColumn.Width(210);barColumn.Height(180);
    barColumn.HorizontalAlignment(HorizontalAlignment::Left);barColumn.VerticalAlignment(VerticalAlignment::Top);
    Controls::ScrollViewer viewer;viewer.Width(258);viewer.Height(180);
    viewer.HorizontalAlignment(HorizontalAlignment::Left);
    viewer.VerticalScrollBarVisibility(Controls::ScrollBarVisibility::Visible);
    Controls::StackPanel longList;longList.Height(800);viewer.Content(longList);
    barColumn.Children().Append(viewer);root.Children().Append(barColumn);
    root.UpdateLayout();BF_ProbePump();root.UpdateLayout();
    auto scrollBar=BF_FindLayoutElement(viewer,L"VerticalScrollBar").as<Controls::Primitives::ScrollBar>();
    const auto stray=BF_FooterBounds(scrollBar,root),barColumnBox=BF_FooterBounds(barColumn,root);
    BF_StartColumns barState;barState.root=winrt::make_weak(root);
    BF_FitAppsScrollBar(barState,barColumn,longList);root.UpdateLayout();
    BF_FitAppsScrollBar(barState,barColumn,longList);root.UpdateLayout();
    viewer.ChangeView(nullptr,80.0,nullptr,true);BF_ProbePump();root.UpdateLayout();
    const auto track=BF_FooterBounds(scrollBar,root);
    const auto columnRight=barColumnBox.X+barColumnBox.Width;
    const bool scrollFits=stray.X+stray.Width>columnRight+20 && track.Width>0 &&
        std::abs(track.X+track.Width-columnRight)<1 && viewer.VerticalOffset()>60;
    unsigned barIndex=0;root.Children().IndexOf(barColumn,barIndex);root.Children().RemoveAt(barIndex);
    if (observed) {
        // This is the production order, including native property watchers.
        // Direct-style fixtures previously restored watchers first and missed
        // exceptions caused by resetting layout while watchers were active.
        Wh_ModSettingsChanged();BF_ProbePump();root.UpdateLayout();
        Wh_ModUninit();MH_DisableHook(MH_ALL_HOOKS);MH_RemoveHook(MH_ALL_HOOKS);
    } else for(unsigned i=0;i<styled.size();++i) CleanupCustomizations(static_cast<ElementId>(10000+i));
    BF_ClearStartSearchButtons();BF_ClearStartColumns();root.UpdateLayout();
    auto pinnedTemplateRoot=Media::VisualTreeHelper::GetParent(pinned).as<Controls::Grid>();
    const bool innerRestored=apps.ItemsPanelRoot().Margin().Left==52&&pinnedTemplateRoot.Padding().Left==32&&
        pinnedTemplateRoot.ColumnDefinitions().GetAt(1).Width().Value==24&&
        Media::VisualTreeHelper::GetParent(BF_FindLayoutElement(root,L"PinnedListHeaderText")).as<FrameworkElement>().Margin().Left==63;
    const bool slotRestored=!outerInset || (Controls::Grid::GetColumn(apps)==1 && Controls::Grid::GetColumnSpan(apps)==1);
    const bool restored=innerRestored&&slotRestored&&Media::VisualTreeHelper::GetParent(appsRoot)==originalParent&&Media::VisualTreeHelper::GetParent(pinnedRoot)==originalParent&&
        appsRoot.ReadLocalValue(FrameworkElement::DataContextProperty())==DependencyProperty::UnsetValue()&&footer.ColumnDefinitions().Size()==3&&
        footer.Children().Size()==3&&tiles[0].MinWidth()==96&&power.Visibility()==Visibility::Visible;
    BF_LocalLayout rejected;
    Controls::Border target;target.Margin({0,0,0,0});rejected.element=winrt::make_weak(target.as<FrameworkElement>());
    rejected.values.emplace_back(FrameworkElement::WidthProperty(),winrt::box_value(L"unavailable original value"));
    rejected.values.emplace_back(FrameworkElement::MarginProperty(),winrt::box_value(Thickness{8,0,8,0}));
    const auto priorErrors=bf_errors.load();rejected.restore();
    const bool restoreContinued=target.Margin().Left==8&&rejected.values.empty()&&bf_errors==priorErrors+1;
    bf_errors=priorErrors;
    const bool passed=oldOverflow&&oldTileOverflow&&columns&&hitboxes&&footerFits&&settingsCentered&&restored&&deferred&&hierarchy&&commands&&folderFits&&folderAppearance&&lateInsets&&restoreContinued&&nativeAnimation&&stableDuringMotion&&bothColumnsVisible&&scrollFits;
    std::ofstream report(output/L"start-layout.json");
    report<<"{\"passed\":"<<passed<<",\"title_letter_icon_aligned\":"<<inkAligned
          <<",\"page_switch_keeps_columns_visible\":"<<bothColumnsVisible
          <<",\"apps_scrollbar_fits\":"<<scrollFits<<",\"scroll_right_edges\":["<<stray.X+stray.Width<<","<<track.X+track.Width<<","<<columnRight<<"]"
          <<",\"pinned_center_error_dip\":["<<iconError<<","<<labelError<<"]"
          <<",\"apps_ink_edges\":["<<headingInk<<","<<letter.X<<","<<appLogo.X<<"],\"apps_edge_hit\":"<<rowEdgesHit
          <<",\"stable_during_motion\":"<<stableDuringMotion<<",\"old_column_overflow\":"<<oldOverflow<<",\"old_hover_overflow\":"<<oldTileOverflow
          <<",\"columns\":"<<columns<<",\"hitboxes\":"<<hitboxes<<",\"footer\":"<<footerFits<<",\"settings_centered\":"<<settingsCentered<<",\"restored\":"<<restored
          <<",\"construction_deferred\":"<<deferred<<",\"native_hierarchy\":"<<hierarchy
          <<",\"real_observer\":"<<observed<<",\"rejected_restore_continued\":"<<restoreContinued<<",\"native_animation\":"<<nativeAnimation
           <<",\"inner_templates_restored\":"<<innerRestored<<",\"core_apps_grid\":"<<coreApps<<",\"late_insets_corrected\":"<<lateInsets
          <<",\"footer_and_popup_commands\":"<<commands
          <<",\"four_columns_unchanged_icons\":"<<hitboxes<<",\"folder_fits\":"<<folderFits<<",\"folder_appearance\":"<<folderAppearance
          <<",\"pinned_edge_hit\":"<<pinnedEdgeHit<<",\"folder_edge_hit\":"<<folderEdgeHit
          <<",\"folder_rect\":["<<folderBox.X<<","<<folderBox.Y<<","<<folderBox.Width<<","<<folderBox.Height<<"]"
          <<",\"folder_surface\":["<<surfaceBox.X<<","<<surfaceBox.Y<<","<<surfaceBox.Width<<","<<surfaceBox.Height<<"]"
          <<",\"folder_title\":["<<titleBox.X<<","<<titleBox.Y<<","<<titleBox.Width<<","<<titleBox.Height<<"]"
          <<",\"pinned_heading_x\":"<<secondHeading.X
          <<",\"pinned_heading_width\":"<<secondHeading.Width<<",\"pinned_heading_alignment\":"<<headingAlignment
           <<",\"apps_items_x\":"<<appsItemsBox.X
           <<",\"apps_rect\":["<<appsBox.X<<","<<appsBox.Y<<","<<appsBox.Width<<","<<appsBox.Height<<"]"
           <<",\"apps_column_rect\":["<<left.X<<","<<left.Y<<","<<left.Width<<","<<left.Height<<"]"
           <<",\"app_item_rect\":["<<appItemBox.X<<","<<appItemBox.Y<<","<<appItemBox.Width<<","<<appItemBox.Height<<"]"
           <<",\"heading_positions\":["<<firstHeading.X<<","<<firstHeading.Y<<","<<secondHeading.X<<","<<secondHeading.Y<<"]"
          <<",\"first_pin\":["<<bounds[0].X<<","<<bounds[0].Y<<","<<bounds[0].Width<<","<<bounds[0].Height<<"]"
          <<",\"first_folder_pin\":["<<folderBoxes[0].X<<","<<folderBoxes[0].Y<<","<<folderBoxes[0].Width<<","<<folderBoxes[0].Height<<"]"
          <<",\"settings_rect\":["<<settingsBox.X<<","<<settingsBox.Y<<","<<settingsBox.Width<<","<<settingsBox.Height<<"]"
          <<",\"settings_icon\":["<<settingsIcon.X<<","<<settingsIcon.Y<<","<<settingsIcon.Width<<","<<settingsIcon.Height<<"]"
          <<",\"search_rect\":["<<searchBox.X<<","<<searchBox.Y<<","<<searchBox.Width<<","<<searchBox.Height<<"]}";
    source.Content(nullptr);source.Close();DestroyWindow(window);return passed;
}
